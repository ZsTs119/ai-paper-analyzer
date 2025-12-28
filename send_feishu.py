# send_feishu.py - Feishu/Lark notification
import os
import sys
import json
import requests
import time
from datetime import datetime

# Read credentials from environment variables
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

def send_feishu_notification(title, content, status="info"):
    """
    Send notification to Feishu Webhook
    
    Args:
        title (str): Message title
        content (str): Message content (can be multi-line)
        status (str): Status type ('success', 'failed', 'info') to determine color
    """
    if not FEISHU_WEBHOOK:
        print("❌ Warning: FEISHU_WEBHOOK environment variable is not set. Skipping Feishu notification.")
        return False
    
    print(f"📨 Sending Feishu notification: {title}")
    
    # Determine color based on status
    # Blue: info, Green: success, Red: failed/error
    template = "blue"
    if status.lower() in ['success', 'ok', 'pass']:
        template = "green"
    elif status.lower() in ['failed', 'error', 'fail']:
        template = "red"
        
    # Construct card message
    # Reference: https://open.feishu.cn/document/ukTMukTMukTM/uMjNwUjLzYMD14yM2ATN
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": template
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"Time: {current_time}"
                        }
                    ]
                }
            ]
        }
    }
    
    try:
        response = requests.post(
            FEISHU_WEBHOOK, 
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") == 0:
            print("✅ Feishu notification sent successfully!")
            return True
        else:
            print(f"❌ Feishu API Error: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to send Feishu notification: {e}")
        return False

def main():
    """Test function for standalone execution"""
    if len(sys.argv) > 1:
        # If arguments provided: python send_feishu.py "Title" "Content"
        title = sys.argv[1]
        content = sys.argv[2] if len(sys.argv) > 2 else "Test content from CLI"
        status = sys.argv[3] if len(sys.argv) > 3 else "info"
    else:
        # Default test
        title = "🔔 Pipeline Notification Test"
        content = "This is a **test message** from the AI Paper Analyzer pipeline.\n\nEverything looks good! 🚀"
        status = "success"
        
    print(f"Test Run: Sending '{title}'...")
    send_feishu_notification(title, content, status)

if __name__ == "__main__":
    main()
