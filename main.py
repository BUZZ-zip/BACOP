import os
import requests
import time
import random
import sys
import urllib3
import argparse

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ANSI color codes
GREEN = '\033[92m'
ORANGE = '\033[93m'
RESET = '\033[0m'

def check_file(file_path, local_root, target_url, match_codes, filter_content, filter_size):
    # Construct relative path
    rel_path = os.path.relpath(file_path, local_root)
    # Ensure forward slashes for URL
    rel_path = rel_path.replace(os.sep, '/')
    
    # Construct full URL
    full_url = f"{target_url.rstrip('/')}/{rel_path}"
    
    headers = {
        'User-Agent': 'YesWeHack-SLCC999'
    }
    
    try:
        # Random delay for WAF evasion (0.1 to 0.2 seconds)
        time.sleep(random.uniform(0.1, 0.2))
        
        # Send GET request
        # verify=False to handle self-signed certs often found in testing environments
        response = requests.get(full_url, headers=headers, timeout=10, verify=False)
        
        # Content filtering
        if filter_content:
            for content_filter in filter_content:
                if content_filter in response.text:
                    return

        # Size filtering
        content_size = len(response.content)
        if filter_size and content_size in filter_size:
            return

        # Status code matching
        if response.status_code in match_codes:
            if response.status_code == 200:
                print(f"{GREEN}[{response.status_code}] [Size: {content_size}] Found: {full_url}{RESET}")
            elif response.status_code == 403:
                print(f"{ORANGE}[{response.status_code}] [Size: {content_size}] Forbidden: {full_url}{RESET}")
            else:
                print(f"[{response.status_code}] [Size: {content_size}] {full_url}")
            
    except requests.exceptions.RequestException:
        # Handle connection errors silently to avoid cluttering output
        pass
    except Exception as e:
        print(f"Error processing {full_url}: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Broken Access Control (BAC) testing tool based on local file mapping.")
    
    parser.add_argument("-u", "--url", required=True, help="Target URL (e.g., http://example.com)")
    parser.add_argument("-d", "--dir", required=True, help="Local directory source (e.g., /path/to/source)")
    parser.add_argument("-fc", "--filter-content", nargs='+', help="List of strings to exclude if found in response text (e.g. 'Access Denied' 'Login')")
    parser.add_argument("-fs", "--filter-size", nargs='+', type=int, help="List of response sizes to exclude (e.g. 0 123)")
    parser.add_argument("-mc", "--match-codes", nargs='+', type=int, default=[200], help="List of status codes to report (default: 200)")

    args = parser.parse_args()

    local_dir = args.dir
    target_url = args.url
    
    # Validate local directory
    if not os.path.isdir(local_dir):
        print(f"Erreur: Le dossier '{local_dir}' n'existe pas ou n'est pas un dossier.")
        sys.exit(1)

    print(f"\nStarting scan on {target_url} based on files in {local_dir}...")
    if args.filter_content:
        print(f"Filtering content containing: {args.filter_content}")
    if args.filter_size:
        print(f"Filtering responses with size: {args.filter_size}")
    print(f"Matching status codes: {args.match_codes}\n")

    try:
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                file_path = os.path.join(root, file)
                check_file(file_path, local_dir, target_url, args.match_codes, args.filter_content, args.filter_size)
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
        sys.exit(0)

if __name__ == "__main__":
    main()
