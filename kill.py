import os
import sys

def main():
    sentinel_path = os.path.join(os.path.dirname(__file__), '.kill_sentinel')
    try:
        with open(sentinel_path, 'w') as f:
            f.write("KILL")
        print(f"Kill signal sent! Sentinel file created at: {sentinel_path}")
    except Exception as e:
        print(f"Failed to send kill signal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
