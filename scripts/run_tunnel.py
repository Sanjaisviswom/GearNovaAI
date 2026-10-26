"""
scripts/run_tunnel.py
─────────────────────
Start ngrok tunnel and keep it running for WhatsApp webhook.
"""
import sys
import time
from pyngrok import ngrok

def main():
    tunnel = ngrok.connect(8000, "http")
    webhook_url = tunnel.public_url + "/webhook"
    print("=" * 60)
    print(f"  NGROK TUNNEL ACTIVE")
    print(f"  Public URL:  {tunnel.public_url}")
    print(f"  Webhook URL: {webhook_url}")
    print(f"")
    print(f"  >> Use this Webhook URL in Meta WhatsApp settings <<")
    print("=" * 60)
    sys.stdout.flush()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down tunnel...")
        ngrok.disconnect(tunnel.public_url)
        ngrok.kill()

if __name__ == "__main__":
    main()
