import os
import requests
import time
import random
import sys
import urllib3
import argparse
import re
from datetime import datetime

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ANSI color codes
COLOR_RESET = '\033[0m'
COLOR_DEFAULT = '\033[0m'
COLOR_ERROR = '\033[31m'  # Red
COLOR_SUCCESS = '\033[32m'  # Green
COLOR_WARN = '\033[33m'  # Orange/Yellow
COLOR_INFO = '\033[34m'  # Blue
COLOR_CYAN = '\033[36m'  # Cyan

def print_banner():
    banner = r"""
  ____    _    ____ ___  ____  
 | __ )  / \  / ___/ _ \/ ___| 
 |  _ \ / _ \| |  | | | \___ \ 
 | |_) / ___ \ |__| |_| |___) |
 |____/_/   \_\____\___/|____/ 
                               
    """
    print(f"{COLOR_CYAN}{banner}{COLOR_RESET}")
    print(f"      {COLOR_WARN}v1.0.0{COLOR_RESET}")
    print(f"{COLOR_CYAN}_{'_'*40}{COLOR_RESET}")
    print()

def parse_range_list(value_str):
    """
    Parses a string like "200,300-305,404" into a set of integers.
    Returns None if input is None or empty.
    """
    if not value_str:
        return None
    
    res = set()
    parts = value_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                res.update(range(start, end + 1))
            except ValueError:
                continue # Ignore malformed ranges
        elif part.lower() == 'all':
            return 'all'
        else:
            try:
                res.add(int(part))
            except ValueError:
                continue
    return res

def parse_headers(header_list):
    headers = {}
    if header_list:
        for h in header_list:
            if ':' in h:
                key, val = h.split(':', 1)
                headers[key.strip()] = val.strip()
    return headers

def match_value(value, criteria, mode='exact'):
    """
    Checks if value matches criteria.
    criteria can be a set (exact/range match), a string (regex), 
    or a comparator string like ">100" or "<100".
    """
    if criteria is None:
        return False
    
    if mode == 'set':
        if criteria == 'all':
            return True
        return value in criteria
    
    elif mode == 'text':
        return criteria in value
    
    elif mode == 'comparator':
        # criteria is like ">100" or "<100"
        try:
            if criteria.startswith('>'):
                return value > int(criteria[1:])
            elif criteria.startswith('<'):
                return value < int(criteria[1:])
            else:
                return value == int(criteria)
        except ValueError:
            return False
            
    return False

def check_conditions(metrics, options, prefix):
    """
    Generic checker for Matcher (-m*) or Filter (-f*) options.
    prefix is 'm' for matchers or 'f' for filters.
    Returns True if the conditions are met based on mode (and/or).
    """
    
    # Map metric keys to option keys (e.g. 'status' -> 'mc')
    # metrics: status, lines, words, size, duration, body
    
    checks = []
    
    # Status Code (-mc / -fc)
    if getattr(options, f'{prefix}c'):
        val = getattr(options, f'{prefix}c')
        checks.append(match_value(metrics['status'], val, 'set'))

    # Lines (-ml / -fl)
    if getattr(options, f'{prefix}l'):
        val = getattr(options, f'{prefix}l')
        checks.append(match_value(metrics['lines'], val, 'set'))
        
    # Words (-mw / -fw)
    if getattr(options, f'{prefix}w'):
        val = getattr(options, f'{prefix}w')
        checks.append(match_value(metrics['words'], val, 'set'))
        
    # Size (-ms / -fs)
    if getattr(options, f'{prefix}s'):
        val = getattr(options, f'{prefix}s')
        checks.append(match_value(metrics['size'], val, 'set'))
        
    # Text (-mr / -fr)
    if getattr(options, f'{prefix}r'):
        val = getattr(options, f'{prefix}r')
        checks.append(match_value(metrics['body'], val, 'text'))
        
    # Time (-mt / -ft)
    if getattr(options, f'{prefix}t'):
        val = getattr(options, f'{prefix}t')
        checks.append(match_value(metrics['duration'], val, 'comparator'))

    if not checks:
        return False if prefix == 'f' else True # If no filters, return False (don't filter). If no matchers, see logic below.
        
    mode = getattr(options, f'{prefix}mode')
    if mode == 'or':
        return any(checks)
    else: # and
        return all(checks)

def process_request(full_url, rel_path, options, headers):
    try:
        # Random delay
        time.sleep(random.uniform(0.1, 0.2))
        
        start_time = time.time()
        
        # Method
        method = options.method.upper()
        
        response = requests.request(
            method, 
            full_url, 
            headers=headers, 
            timeout=10, 
            verify=False,
            allow_redirects=options.follow_redirects
        )
        
        duration = int((time.time() - start_time) * 1000)
        
        # Collect Metrics
        content = response.content
        text = response.text
        
        metrics = {
            'status': response.status_code,
            'size': len(content),
            'words': len(text.split()),
            'lines': len(text.splitlines()),
            'duration': duration,
            'body': text
        }
        
        # 1. Check Filters
        # Use default filter logic: if NO filters specified, is_filtered=False.
        # If filters specified, apply them.
        has_filters = any([options.fc, options.fl, options.fw, options.fs, options.fr, options.ft])
        if has_filters:
            if check_conditions(metrics, options, 'f'):
                return # Filtered out
        
        # 2. Check Matchers
        # Logic: If NO matchers specified, match defaults?
        # Argparse handles defaults for -mc. So -mc is almost always present.
        # If user explicitly disabled mc (e.g. -mc ""), we might need to handle that.
        # But generally, we check if it matches.
        
        if check_conditions(metrics, options, 'm'):
            # Print Result
            status_color = COLOR_DEFAULT
            if metrics['status'] in [200, 204]:
                status_color = COLOR_SUCCESS
            elif metrics['status'] in [301, 302, 307]:
                status_color = COLOR_INFO
            elif metrics['status'] in [401, 403]:
                status_color = COLOR_WARN
            elif metrics['status'] >= 500:
                status_color = COLOR_ERROR
            
            size_fmt = metrics['size']
            words_fmt = metrics['words']
            lines_fmt = metrics['lines']
            
            print(f"{rel_path:<30} {COLOR_RESET}[Status: {status_color}{metrics['status']}{COLOR_RESET}, Size: {size_fmt}, Words: {words_fmt}, Lines: {lines_fmt}, Duration: {duration}ms]")

    except requests.exceptions.RequestException:
        pass
    except Exception as e:
        print(f"{COLOR_ERROR}Error processing {full_url}: {e}{COLOR_RESET}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="Broken Access Control (BAC) testing tool", formatter_class=argparse.RawTextHelpFormatter)
    
    # General Options
    parser.add_argument("-u", "--url", required=True, help="Target URL")
    parser.add_argument("-d", "--dir", required=True, help="Local directory source")
    parser.add_argument("-H", "--header", action='append', help="Header 'Name: Value', separated by colon. Multiple -H flags are accepted.")
    parser.add_argument("-X", "--method", default="GET", help="HTTP method to use (default: GET)")
    parser.add_argument("-r", "--follow-redirects", action='store_true', help="Follow redirects (default: false)")
    
    # Matcher Options
    group_m = parser.add_argument_group('MATCHER OPTIONS')
    group_m.add_argument("-mc", default="200,204,301,302,307,401,403,405,500", help="Match HTTP status codes, or 'all' (default: common codes)")
    group_m.add_argument("-ml", help="Match amount of lines in response")
    group_m.add_argument("-mw", help="Match amount of words in response")
    group_m.add_argument("-ms", help="Match HTTP response size")
    group_m.add_argument("-mr", help="Match text in response")
    group_m.add_argument("-mt", help="Match milliseconds to first response byte (>100 or <100)")
    group_m.add_argument("-mmode", default="and", choices=['or', 'and'], help="Matcher set operator (default: and)")
    
    # Filter Options
    group_f = parser.add_argument_group('FILTER OPTIONS')
    group_f.add_argument("-fc", help="Filter HTTP status codes")
    group_f.add_argument("-fl", help="Filter by amount of lines")
    group_f.add_argument("-fw", help="Filter by amount of words")
    group_f.add_argument("-fs", help="Filter HTTP response size")
    group_f.add_argument("-fr", help="Filter text in response")
    group_f.add_argument("-ft", help="Filter milliseconds to first response byte")
    group_f.add_argument("-fmode", default="or", choices=['or', 'and'], help="Filter set operator (default: or)")

    args = parser.parse_args()

    # Pre-process arguments
    # 1. Parse Ranges/Lists
    args.mc = parse_range_list(args.mc)
    args.ml = parse_range_list(args.ml)
    args.mw = parse_range_list(args.mw)
    args.ms = parse_range_list(args.ms)
    
    args.fc = parse_range_list(args.fc)
    args.fl = parse_range_list(args.fl)
    args.fw = parse_range_list(args.fw)
    args.fs = parse_range_list(args.fs)
    
    # 2. Prepare headers
    headers = parse_headers(args.header)
    if 'User-Agent' not in headers:
        headers['User-Agent'] = "YesWeHack-SLCC999" # Default UA if not provided in headers
        
    # Validate Dir
    if not os.path.isdir(args.dir):
        print(f"{COLOR_ERROR}Erreur: Le dossier '{args.dir}' n'existe pas.{COLOR_RESET}")
        sys.exit(1)

    print_banner()
    
    # Print Configuration
    print(f" :: {COLOR_INFO}Method{COLOR_RESET}           : {args.method}")
    print(f" :: {COLOR_INFO}URL{COLOR_RESET}              : {args.url}")
    print(f" :: {COLOR_INFO}Wiki{COLOR_RESET}             : {args.dir}")
    print(f" :: {COLOR_INFO}Follow Redirects{COLOR_RESET} : {args.follow_redirects}")
    for k, v in headers.items():
        print(f" :: {COLOR_INFO}Header{COLOR_RESET}           : {k}: {v}")
    
    print(f"{COLOR_CYAN}_{'_'*40}{COLOR_RESET}")
    print()

    try:
        for root, dirs, files in os.walk(args.dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Construct relative path
                rel_path = os.path.relpath(file_path, args.dir)
                rel_path = rel_path.replace(os.sep, '/')
                full_url = f"{args.url.rstrip('/')}/{rel_path}"
                
                process_request(full_url, rel_path, args, headers)
                
    except KeyboardInterrupt:
        print(f"\n{COLOR_WARN}Scan interrupted by user.{COLOR_RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
