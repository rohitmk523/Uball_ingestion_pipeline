import ezdxf
import json
import re
from datetime import datetime
import math

def parse_dxf(dxf_path):
    """
    Parses the DXF file to extract court geometry.
    Returns a list of lines and arcs.
    """
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        
        geometry = []
        
        # Parse Lines
        for line in msp.query('LINE'):
            geometry.append({
                'type': 'line',
                'start': {'x': line.dxf.start.x, 'y': line.dxf.start.y},
                'end': {'x': line.dxf.end.x, 'y': line.dxf.end.y},
                'layer': line.dxf.layer
            })
            
        # Parse Polylines (convert to lines)
        for polyline in msp.query('POLYLINE'):
            points = list(polyline.points())
            for i in range(len(points) - 1):
                geometry.append({
                    'type': 'line',
                    'start': {'x': points[i].x, 'y': points[i].y},
                    'end': {'x': points[i+1].x, 'y': points[i+1].y},
                    'layer': polyline.dxf.layer
                })
            # Close loop if closed
            if polyline.is_closed:
                 geometry.append({
                    'type': 'line',
                    'start': {'x': points[-1].x, 'y': points[-1].y},
                    'end': {'x': points[0].x, 'y': points[0].y},
                    'layer': polyline.dxf.layer
                })

        # Parse Circles
        for circle in msp.query('CIRCLE'):
             geometry.append({
                'type': 'circle',
                'center': {'x': circle.dxf.center.x, 'y': circle.dxf.center.y},
                'radius': circle.dxf.radius,
                'layer': circle.dxf.layer
            })

        # Parse Arcs
        for arc in msp.query('ARC'):
             geometry.append({
                'type': 'arc',
                'center': {'x': arc.dxf.center.x, 'y': arc.dxf.center.y},
                'radius': arc.dxf.radius,
                'start_angle': arc.dxf.start_angle,
                'end_angle': arc.dxf.end_angle,
                'layer': arc.dxf.layer
            })
            
        return geometry
    except Exception as e:
        print(f"Error parsing DXF: {e}")
        return []

def parse_logs(log_path):
    """
    Parses the log file and resamples data to fixed 30 FPS (33.33ms).
    Returns a dictionary of frame indices to tag positions.
    """
    raw_data = {}
    
    # Regex to parse log line
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| Tag (\d+) \| X=(\d+) \| Y=(\d+) \| Timestamp=(\d+)')
    
    print("Reading raw logs...")
    try:
        with open(log_path, 'r') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    dt_str, tag_id, x, y, ts = match.groups()
                    
                    # Parse datetime to timestamp (seconds)
                    dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S.%f')
                    timestamp = dt.timestamp()
                    
                    if tag_id not in raw_data:
                        raw_data[tag_id] = []
                    
                    raw_data[tag_id].append({
                        'ts': timestamp,
                        'x': int(x),
                        'y': int(y)
                    })
    except Exception as e:
        print(f"Error parsing logs: {e}")
        return {}

    print("Resampling to 30 FPS...")
    resampled_data = {}
    
    # Find global start and end time
    all_timestamps = [p['ts'] for tag_points in raw_data.values() for p in tag_points]
    if not all_timestamps:
        return {}
        
    start_time = min(all_timestamps)
    end_time = max(all_timestamps)
    duration = end_time - start_time
    
    # 30 FPS = 1/30 seconds per frame
    FRAME_DURATION = 1.0 / 30.0
    total_frames = int(duration / FRAME_DURATION)
    
    print(f"Duration: {duration:.2f}s, Total Frames: {total_frames}")
    
    for frame_idx in range(total_frames):
        current_time = start_time + (frame_idx * FRAME_DURATION)
        frame_key = f"frame_{frame_idx}"
        resampled_data[frame_key] = []
        
        for tag_id, points in raw_data.items():
            # Find points surrounding current_time
            # This assumes points are sorted by timestamp (which they are from log read)
            
            # Optimization: We could track index per tag, but for now simple search
            # Binary search would be better, but linear scan from last known index is best for sequential access.
            # Let's just do a simple linear search for now, assuming not too many points per tag?
            # Actually, points list can be huge. Let's use bisect or just smart indexing.
            
            # Simple approach: Filter points within a small window? No, we need interpolation.
            # Let's use numpy-style interpolation logic but in pure python for simplicity if possible.
            
            # Find the first point > current_time
            # We can optimize this by remembering the last index used for this tag.
            # But `points` is list of dicts.
            
            # Let's just iterate through points and find the interval.
            # Since we iterate frames sequentially, we can keep a pointer for each tag.
            if not hasattr(parse_logs, 'tag_pointers'):
                parse_logs.tag_pointers = {t: 0 for t in raw_data.keys()}
            
            idx = parse_logs.tag_pointers[tag_id]
            
            # Advance pointer until we find the interval or run out
            while idx < len(points) - 1 and points[idx+1]['ts'] < current_time:
                idx += 1
            
            parse_logs.tag_pointers[tag_id] = idx
            
            if idx >= len(points) - 1:
                # End of data for this tag
                continue
                
            p1 = points[idx]
            p2 = points[idx+1]
            
            # Check if current_time is within [p1, p2]
            if p1['ts'] <= current_time <= p2['ts']:
                # Interpolate
                t_diff = p2['ts'] - p1['ts']
                if t_diff > 0:
                    ratio = (current_time - p1['ts']) / t_diff
                    
                    # Linear interpolation
                    new_x = p1['x'] + (p2['x'] - p1['x']) * ratio
                    new_y = p1['y'] + (p2['y'] - p1['y']) * ratio
                    
                    resampled_data[frame_key].append({
                        'tag_id': tag_id,
                        'x': new_x,
                        'y': new_y
                    })
            elif current_time < p1['ts']:
                # Before first point (shouldn't happen with sequential scan but safe to handle)
                pass
            else:
                # After last point
                pass

    # Reset pointers for next run if needed (though we re-init raw_data locally)
    parse_logs.tag_pointers = {}
    
    return resampled_data

def main():
    dxf_path = 'court_2.dxf'
    log_path = 'session_1763778442483.log'
    output_path = 'app/static/game_data.json'
    
    print("Parsing DXF...")
    court_geometry = parse_dxf(dxf_path)
    
    print("Parsing Logs...")
    log_data = parse_logs(log_path)
    
    # Calculate bounding box for logs to help with auto-scaling
    min_x, max_x = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    
    for frame in log_data.values():
        for tag in frame:
            min_x = min(min_x, tag['x'])
            max_x = max(max_x, tag['x'])
            min_y = min(min_y, tag['y'])
            max_y = max(max_y, tag['y'])
            
    log_bounds = {
        'min_x': min_x, 'max_x': max_x,
        'min_y': min_y, 'max_y': max_y
    }
    
    # Calculate bounding box for court
    c_min_x, c_max_x = float('inf'), float('-inf')
    c_min_y, c_max_y = float('inf'), float('-inf')
    
    # Simple bounding box for lines/arcs (ignoring arc curvature for simplicity of initial view)
    for item in court_geometry:
        if item['type'] == 'line':
            c_min_x = min(c_min_x, item['start']['x'], item['end']['x'])
            c_max_x = max(c_max_x, item['start']['x'], item['end']['x'])
            c_min_y = min(c_min_y, item['start']['y'], item['end']['y'])
            c_max_y = max(c_max_y, item['start']['y'], item['end']['y'])
        elif item['type'] in ['circle', 'arc']:
             c_min_x = min(c_min_x, item['center']['x'] - item['radius'])
             c_max_x = max(c_max_x, item['center']['x'] + item['radius'])
             c_min_y = min(c_min_y, item['center']['y'] - item['radius'])
             c_max_y = max(c_max_y, item['center']['y'] + item['radius'])

    court_bounds = {
        'min_x': c_min_x, 'max_x': c_max_x,
        'min_y': c_min_y, 'max_y': c_max_y
    }

    output = {
        'court': court_geometry,
        'court_bounds': court_bounds,
        'logs': log_data,
        'log_bounds': log_bounds
    }
    
    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f)
        
    print("Done.")

if __name__ == "__main__":
    main()
