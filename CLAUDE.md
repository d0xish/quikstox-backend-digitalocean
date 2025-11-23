# QuikStox Backend - Deployment Documentation

This document describes the auto-deployment setup for the QuikStox backend to DigitalOcean Droplet.

## Overview

The backend automatically deploys to a DigitalOcean Droplet whenever code is pushed to the `main` branch of the GitHub repository.

## Deployment Architecture

- **Platform**: DigitalOcean Droplet (Ubuntu)
- **Server Location**: `128.199.5.245`
- **Application Path**: `/var/www/quikstox`
- **Process Manager**: systemd (service: `quikstox-backend`)
- **Web Server**: Uvicorn (FastAPI)
- **Port**: 8000
- **Auto-deployment**: GitHub Actions

## Components

### 1. Systemd Service

The backend runs as a systemd service for reliable process management and automatic restarts.

**Service file location**: `/etc/systemd/system/quikstox-backend.service`

**Key features**:
- Automatically starts on server boot
- Restarts on failure (10-second delay)
- Managed by systemd (no more Supervisor)

**Useful commands**:
```bash
# Check service status
systemctl status quikstox-backend

# Restart service
systemctl restart quikstox-backend

# View logs
journalctl -u quikstox-backend -f

# Stop service
systemctl stop quikstox-backend

# Start service
systemctl start quikstox-backend
```

### 2. GitHub Actions Workflow

**Workflow file**: `.github/workflows/deploy.yml`

**Triggers**:
- Automatic: Any push to `main` branch
- Manual: Via GitHub Actions UI (workflow_dispatch)

**Deployment steps**:
1. SSH into Droplet using secure key authentication
2. Pull latest code from GitHub
3. Activate Python virtual environment
4. Install/update dependencies from requirements.txt
5. Restart the systemd service

**GitHub Secrets required**:
- `SSH_PRIVATE_KEY`: SSH private key for authentication
- `DROPLET_IP`: Server IP address (128.199.5.245)
- `DROPLET_USER`: SSH username (root)

### 3. SSH Authentication

**SSH key location on Droplet**: `~/.ssh/github_actions_deploy`

The public key is added to `~/.ssh/authorized_keys` to allow GitHub Actions to SSH in securely without passwords.

## Setup History

### Previous Configuration
- Originally used **Supervisor** for process management
- Config file was at `/etc/supervisor/conf.d/quikstox.conf` (now removed)

### Current Configuration (as of today)
- Switched to **systemd** for better integration and reliability
- Configured GitHub Actions for automated deployments
- Set up SSH key-based authentication for secure deployments

## Free Cash Flow Feature

### What was added
Added Free Cash Flow to Firm (TTM) calculation and display feature.

**Backend changes** (`stock_analyzer.py`):
- Fetches cash flow data from yfinance
- Uses pre-calculated "Free Cash Flow" field when available
- Falls back to manual calculation: Operating Cash Flow - Capital Expenditures
- Supports quarterly TTM (trailing twelve months) calculation
- Falls back to annual data if quarterly unavailable
- Returns structured data: `{value, note, error}`
- Comprehensive error handling

**Frontend changes** (`StockResults.jsx`):
- Added `formatFCF()` function for formatting
- Displays values with M suffix (< $1B) or B suffix (≥ $1B)
- Shows negative values in red
- Displays asterisk with tooltip for non-standard TTM calculations
- Shows "Data unavailable" with error details in title attribute

## How to Deploy Manually

If you need to deploy without using GitHub Actions:

1. SSH into the Droplet:
   ```bash
   ssh root@128.199.5.245
   ```

2. Navigate to the application directory:
   ```bash
   cd /var/www/quikstox
   ```

3. Pull latest changes:
   ```bash
   git pull origin main
   ```

4. Update dependencies:
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. Restart the service:
   ```bash
   systemctl restart quikstox-backend
   ```

## Troubleshooting

### Check if the backend is running
```bash
systemctl is-active quikstox-backend
```

### View recent logs
```bash
journalctl -u quikstox-backend -n 50 --no-pager
```

### Check if uvicorn is running
```bash
ps aux | grep uvicorn
```

### Test the API
```bash
curl http://128.199.5.245:8000
```

### If deployment fails
1. Check GitHub Actions logs at: https://github.com/d0xish/quikstox-backend-digitalocean/actions
2. SSH into Droplet and check service status
3. Review application logs in `/var/www/quikstox/stock_analyzer.log`
4. Check systemd logs with `journalctl -u quikstox-backend`

### If the service won't start
1. Check for syntax errors: `python -m py_compile main.py`
2. Verify virtual environment: `source venv/bin/activate && which python`
3. Test manually: `cd /var/www/quikstox && venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000`

## Environment Variables

The backend uses environment variables stored in `/var/www/quikstox/.env`:
- API keys
- Configuration settings
- **Important**: Never commit `.env` to Git - it's in `.gitignore`

## Related Repositories

- **Frontend**: https://github.com/d0xish/quikstox-frontend-netlify (auto-deploys to Netlify)
- **Backend**: https://github.com/d0xish/quikstox-backend-digitalocean (auto-deploys to Droplet)

## Notes

- The Droplet has limited resources (1 vCPU, 512MB RAM) - monitor performance
- GitHub shows 2 high vulnerabilities - consider reviewing Dependabot alerts
- Auto-deployment typically completes in 30-60 seconds
- The systemd service has a 10-second restart delay to prevent boot loops
