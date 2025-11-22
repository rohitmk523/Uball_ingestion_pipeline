# Operations Guide

## 🚀 Deployment

### Option 1: Automated Deployment (Recommended)
We have set up a GitHub Actions pipeline. To deploy changes:
1.  Commit and push your changes to the `main` branch.
2.  The pipeline will automatically run tests.
3.  If tests pass, it will deploy to EC2 (requires configuration, see below).

**Prerequisites for Auto-Deploy:**
Add these secrets to your GitHub Repository (Settings -> Secrets and variables -> Actions):
- `EC2_HOST`: Your EC2 IP address (e.g., `13.218.240.175`)
- `EC2_SSH_KEY`: The content of your `.pem` file.

### Option 2: Manual Deployment
If you prefer to deploy manually:

1.  **SSH into the instance**:
    ```bash
    ssh -i uball-basketball-key.pem ubuntu@<EC2_IP>
    ```

2.  **Pull latest changes**:
    ```bash
    cd ~/Uball_ingestion_pipeline
    git pull origin main
    ```

3.  **Update dependencies (if needed)**:
    ```bash
    source venv/bin/activate
    pip install -r requirements.txt
    ```

4.  **Restart the service**:
    ```bash
    sudo systemctl restart basketball-pipeline
    ```

## 🔍 Monitoring & Logs

### Check Service Status
To see if the pipeline is running:
```bash
sudo systemctl status basketball-pipeline
```

### View Application Logs
To watch the logs in real-time (like `tail -f`):
```bash
tail -f ~/Uball_ingestion_pipeline/logs/pipeline.log
```
*Note: This log file rotates automatically, so it won't fill up the disk.*

### Health Check
You can check the health of the service remotely or locally:
```bash
curl http://localhost:8000/health
```
Response:
```json
{
  "status": "healthy",
  "gpu_available": false,
  "disk_space_gb": 45.2,
  "active_connections": 0,
  "processing_active": false
}
```

## 🛠 Troubleshooting

**Service fails to start?**
Check the system logs for startup errors:
```bash
sudo journalctl -u basketball-pipeline -n 50 --no-pager
```

**Permission errors?**
Ensure the `ubuntu` user owns the directory:
```bash
sudo chown -R ubuntu:ubuntu ~/Uball_ingestion_pipeline
```
