"""
Deploy Module - GitHub Webhook Auto-Deploy
Receives push events from GitHub and triggers deployment.
"""

import hashlib
import hmac
import subprocess
import os
from flask import request, jsonify, current_app
from modules.deploy import deploy_bp


@deploy_bp.route('/deploy/webhook', methods=['POST'])
def github_webhook():
    """
    GitHub webhook endpoint for auto-deploy.
    Verifies HMAC-SHA256 signature, checks branch, runs deploy script.
    """
    secret = current_app.config.get('GITHUB_WEBHOOK_SECRET')
    if not secret:
        return jsonify({'status': 'error', 'message': 'Webhook not configured'}), 500

    # Verify signature
    signature = request.headers.get('X-Hub-Signature-256')
    if not signature:
        return jsonify({'status': 'error', 'message': 'Missing signature'}), 403

    payload = request.get_data()
    expected_sig = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        return jsonify({'status': 'error', 'message': 'Invalid signature'}), 403

    # Parse payload
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400

    # Only deploy on push to main
    ref = data.get('ref', '')
    if ref != 'refs/heads/main':
        return jsonify({'status': 'ignored', 'message': f'Push to {ref}, not main'}), 200

    # Run deploy script in background
    project_root = os.path.abspath(os.path.join(current_app.root_path, '..', '..'))
    deploy_script = os.path.join(project_root, 'deploy.sh')

    if not os.path.isfile(deploy_script):
        return jsonify({'status': 'error', 'message': 'Deploy script not found'}), 500

    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'deploy.log')

    with open(log_file, 'a') as log:
        subprocess.Popen(
            ['bash', deploy_script],
            stdout=log,
            stderr=log,
            cwd=os.path.dirname(deploy_script),
        )

    pusher = data.get('pusher', {}).get('name', 'unknown')
    return jsonify({
        'status': 'ok',
        'message': f'Deploy triggered by {pusher}',
    }), 200
