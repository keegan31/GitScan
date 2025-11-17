#!/usr/bin/env python3
import requests
import json
import re
import sys
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import argparse
from colorama import Fore, Style, init

init(autoreset=True)

class GitScan:
    def __init__(self, token, threads=5):
        self.token = token
        self.threads = threads
        self.headers = {
            'Authorization': f'token {token}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.found_data = {
            'emails': set(),
            'repos': [],
            'organizations': [],
            'events': [],
            'gists': [],
            'user_info': {}
        }
        self.lock = threading.Lock()

    def print_banner(self):
        banner = f"""
        {Fore.MAGENTA}
⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣠⣤⣤⣶⣶⣶⣤⣤⣄⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⣠⣶⣿⣿⡿⣿⣿⣿⡿⠋⠉⠀⠀⠉⠙⢿⣿⣿⡿⣿⣿⣷⣦⡀⠀⠀⠀
⠀⢀⣼⣿⣿⠟⠁⢠⣿⣿⠏⠀⠀⢠⣤⣤⡀⠀⠀⢻⣿⣿⡀⠙⢿⣿⣿⣦⠀⠀
⣰⣿⣿⡟⠁⠀⠀⢸⣿⣿⠀⠀⠀⢿⣿⣿⡟⠀⠀⠈⣿⣿⡇⠀⠀⠙⣿⣿⣷⡄
⠈⠻⣿⣿⣦⣄⠀⠸⣿⣿⣆⠀⠀⠀⠉⠉⠀⠀⠀⣸⣿⣿⠃⢀⣤⣾⣿⣿⠟⠁
⠀⠀⠈⠻⣿⣿⣿⣶⣿⣿⣿⣦⣄⠀⠀⠀⢀⣠⣾⣿⣿⣿⣾⣿⣿⡿⠋⠁⠀⠀
⠀⠀⠀⠀⠀⠙⠻⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠛⠁⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠛⠛⠿⠿⠿⠿⠿⠿⠛⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀
╔══════════════════════════════════╗
║☆          GITSCAN               ~║
║          OSINT TOOL              ║
║~   TARGET & EMAIL DISCOVERY     ☆║
╚══════════════════════════════════╝
        {Style.RESET_ALL}
        """
        print(banner)

    def log_info(self, message):
        print(f"{Fore.MAGENTA}[INFO]{Style.RESET_ALL} {message}")

    def log_warning(self, message):
        print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} {message}")

    def log_error(self, message):
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")

    def log_success(self, message):
        print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {message}")

    def get_all_repos(self, username):
        self.log_info(f"Scanning all repositories for: {username}")
        
        repos = []
        page = 1
        per_page = 100
        
        while True:
            url = f"https://api.github.com/users/{username}/repos?page={page}&per_page={per_page}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                page_repos = response.json()
                if not page_repos:
                    break
                
                repos.extend(page_repos)
                self.log_info(f"Page {page}: Found {len(page_repos)} repositories")
                
                if len(page_repos) < per_page:
                    break
                    
                page += 1
                time.sleep(0.5)
                
            else:
                self.log_error(f"Error retrieving page {page}: {response.status_code}")
                break
        
        self.log_success(f"Total repositories found: {len(repos)}")
        return repos

    def scan_single_repo(self, args):
        username, repo, index, total = args
        repo_name = repo['name']
        
        self.log_info(f"[{index}/{total}] Scanning: {repo_name}")
        
        repo_info = {
            'name': repo['name'],
            'full_name': repo['full_name'],
            'description': repo.get('description', 'N/A'),
            'language': repo.get('language', 'N/A'),
            'stars': repo['stargazers_count'],
            'forks': repo['forks_count'],
            'watchers': repo['watchers_count'],
            'size': repo['size'],
            'created': repo['created_at'],
            'updated': repo['updated_at'],
            'pushed': repo['pushed_at'],
            'url': repo['html_url'],
            'clone_url': repo['clone_url']
        }
        
        with self.lock:
            self.found_data['repos'].append(repo_info)
        
        commits_emails = self.scan_repo_commits(username, repo_name)
        code_emails = self.scan_repo_code(username, repo_name)
        
        all_emails = commits_emails.union(code_emails)
        with self.lock:
            self.found_data['emails'].update(all_emails)
        
        self.scan_repo_contents(username, repo_name)
        
        return all_emails

    def scan_repositories(self, username, repos):
        self.log_info(f"Analyzing {len(repos)} repositories with {self.threads} threads...")
        
        emails_found = set()
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            args_list = [(username, repo, i+1, len(repos)) for i, repo in enumerate(repos)]
            results = executor.map(self.scan_single_repo, args_list)
            
            for result in results:
                emails_found.update(result)
        
        return repos

    def scan_repo_commits(self, username, repo_name):
        emails_found = set()
        
        try:
            commits_url = f"https://api.github.com/repos/{username}/{repo_name}/commits"
            commits_response = requests.get(commits_url, headers=self.headers)
            
            if commits_response.status_code == 200:
                commits = commits_response.json()
                
                for commit in commits[:50]:
                    commit_data = commit.get('commit', {})
                    author = commit_data.get('author', {})
                    committer = commit_data.get('committer', {})
                    
                    author_email = author.get('email')
                    committer_email = committer.get('email')
                    
                    if author_email and self.is_personal_email(author_email):
                        emails_found.add(author_email)
                    if committer_email and self.is_personal_email(committer_email):
                        emails_found.add(committer_email)
                        
        except Exception as e:
            self.log_error(f"Error scanning commits in {repo_name}: {e}")
            
        return emails_found

    def scan_repo_code(self, username, repo_name):
        emails_found = set()
        
        try:
            search_url = f"https://api.github.com/search/code?q=user:{username}+repo:{username}/{repo_name}+%22@%22"
            search_response = requests.get(search_url, headers=self.headers)
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                
                for item in search_data.get('items', [])[:10]:
                    file_url = item['html_url']
                    raw_url = file_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                    
                    try:
                        content_response = requests.get(raw_url)
                        if content_response.status_code == 200:
                            content = content_response.text
                            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                            found_emails = re.findall(email_pattern, content)
                            
                            for email in found_emails:
                                if self.is_personal_email(email):
                                    emails_found.add(email)
                    
                    except Exception:
                        continue
                        
        except Exception as e:
            self.log_error(f"Error scanning code in {repo_name}: {e}")
            
        return emails_found

    def scan_repo_contents(self, username, repo_name):
        try:
            contents_url = f"https://api.github.com/repos/{username}/{repo_name}/contents"
            contents_response = requests.get(contents_url, headers=self.headers)
            
            if contents_response.status_code == 200:
                contents = contents_response.json()
                
        except Exception:
            pass

    def get_user_info(self, username):
        self.log_info("Retrieving user information...")
        
        url = f"https://api.github.com/users/{username}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            user_data = response.json()
            self.found_data['user_info'] = user_data
            
            self.log_success(f"User found: {user_data.get('login')}")
            print(f"Name: {user_data.get('name', 'N/A')}")
            print(f"Public Email: {user_data.get('email', 'N/A')}")
            print(f"Company: {user_data.get('company', 'N/A')}")
            print(f"Location: {user_data.get('location', 'N/A')}")
            print(f"Blog/Website: {user_data.get('blog', 'N/A')}")
            print(f"Bio: {user_data.get('bio', 'N/A')}")
            print(f"Public Repos: {user_data.get('public_repos', 0)}")
            print(f"Followers: {user_data.get('followers', 0)}")
            print(f"Following: {user_data.get('following', 0)}")
            print(f"Account Created: {user_data.get('created_at', 'N/A')}")
            print(f"Last Updated: {user_data.get('updated_at', 'N/A')}")
            
            if user_data.get('email'):
                self.found_data['emails'].add(user_data['email'])
                
            return user_data
        else:
            self.log_error(f"User not found: {response.status_code}")
            return None

    def get_user_events(self, username):
        self.log_info("Analyzing recent activities...")
        
        url = f"https://api.github.com/users/{username}/events/public"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            events = response.json()
            self.log_success(f"Found {len(events)} public events")
            
            event_types = {}
            for event in events[:20]:
                event_type = event['type']
                event_types[event_type] = event_types.get(event_type, 0) + 1
                
                self.found_data['events'].append({
                    'type': event_type,
                    'repo': event['repo']['name'] if 'repo' in event else 'N/A',
                    'created_at': event['created_at']
                })
            
            self.log_info("Event distribution:")
            for event_type, count in event_types.items():
                print(f"     {event_type}: {count}")
                
            return events
        else:
            self.log_error(f"Failed to retrieve events: {response.status_code}")
            return []

    def get_user_organizations(self, username):
        self.log_info("Checking organizations...")
        
        url = f"https://api.github.com/users/{username}/orgs"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            orgs = response.json()
            self.log_success(f"Found {len(orgs)} organizations")
            
            for org in orgs:
                org_info = {
                    'name': org['login'],
                    'description': org.get('description', 'N/A')
                }
                self.found_data['organizations'].append(org_info)
                print(f"   {org['login']}")
            
            return orgs
        else:
            self.log_warning("Failed to retrieve organization information")
            return []

    def get_user_gists(self, username):
        self.log_info("Scanning gists...")
        
        url = f"https://api.github.com/users/{username}/gists"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            gists = response.json()
            self.log_success(f"Found {len(gists)} gists")
            
            for gist in gists[:5]:
                gist_info = {
                    'id': gist['id'],
                    'description': gist.get('description', 'N/A'),
                    'files': list(gist['files'].keys()),
                    'created_at': gist['created_at']
                }
                self.found_data['gists'].append(gist_info)
                print(f"   {gist['id']} - {len(gist['files'])} files")
            
            return gists
        else:
            self.log_warning("Failed to retrieve gists")
            return []
    def is_personal_email(self, email):
        corporate_domains = [
         'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 'icloud.com', 'mail.com',
         'protonmail.com', 'proton.me', 'tutanota.com', 'tuta.io', 'pm.me', 'protonmail.ch', 'tutanota.de',
         'gmx.com', 'gmx.de', 'gmx.net', 'web.de', 'yandex.com', 'yandex.ru', 'mail.ru', 'rambler.ru', 'seznam.cz',
         'fastmail.com', 'zoho.com', 'hushmail.com', 'keemail.me', 'orange.fr', 'free.fr', 'laposte.net', 'sfr.fr',
         'libero.it', 'alice.it', 'virgilio.it', 'wp.pl', 'onet.pl', 'interia.pl', 'mail.ee', 'zone.ee',
         'mail.hu', 'freemail.hu', 'azet.sk', 'zoznam.sk', 'email.cz', 'centrum.cz', 'bk.ru', 'inbox.ru', 'list.ru',
         'disroot.org', 'riseup.net', 'cock.li', 'autistici.org', 'gmail.co.uk', 'yahoo.co.uk', 'hotmail.co.uk',
         'gmail.de', 'yahoo.de', 'hotmail.de', 'gmail.fr', 'yahoo.fr', 'hotmail.fr', 'gmail.it', 'yahoo.it', 'hotmail.it',
         'gmail.es', 'yahoo.es', 'hotmail.es', 'inbox.com', 'lycos.com', 'excite.com', 'hush.com', 'juno.com',
         'earthlink.net', 'aim.com', 'btinternet.com', 'ntlworld.com', 'blueyonder.co.uk', 'talktalk.net',
         'vtext.com', 'tmomail.net', 'messaging.sprintpcs.com', 'vmobl.com', 'mmst5.tracfone.com', 'mymetropcs.com',
         'edu.com', 'alumni.', '.ac.', '.edu.'
      ] 
        domain = email.split('@')[-1].lower()
        return domain in corporate_domains

    def save_report(self, username):
        filename = f"{username}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("GITSCAN OSINT REPORT\n")
            f.write("="*60 + "\n")
            
            f.write(f"\nTARGET: {username}\n")
            f.write(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            f.write(f"\nUSER INFORMATION\n")
            f.write("-" * 40 + "\n")
            user_info = self.found_data['user_info']
            f.write(f"Username: {user_info.get('login', 'N/A')}\n")
            f.write(f"Name: {user_info.get('name', 'N/A')}\n")
            f.write(f"Company: {user_info.get('company', 'N/A')}\n")
            f.write(f"Location: {user_info.get('location', 'N/A')}\n")
            f.write(f"Blog: {user_info.get('blog', 'N/A')}\n")
            f.write(f"Bio: {user_info.get('bio', 'N/A')}\n")
            f.write(f"Followers: {user_info.get('followers', 0)}\n")
            f.write(f"Following: {user_info.get('following', 0)}\n")
            f.write(f"Public Repos: {user_info.get('public_repos', 0)}\n")
            f.write(f"Account Created: {user_info.get('created_at', 'N/A')}\n")
            
            f.write(f"\nFOUND EMAILS ({len(self.found_data['emails'])})\n")
            f.write("-" * 40 + "\n")
            for email in self.found_data['emails']:
                f.write(f"{email}\n")
            
            f.write(f"\nREPOSITORIES ({len(self.found_data['repos'])})\n")
            f.write("-" * 40 + "\n")
            for repo in self.found_data['repos']:
                f.write(f"Name: {repo['name']}\n")
                f.write(f"Description: {repo['description']}\n")
                f.write(f"Language: {repo['language']}\n")
                f.write(f"Stars: {repo['stars']} | Forks: {repo['forks']}\n")
                f.write(f"URL: {repo['url']}\n")
                f.write(f"Last Updated: {repo['updated']}\n")
                f.write("-" * 20 + "\n")
            
            f.write(f"\nORGANIZATIONS ({len(self.found_data['organizations'])})\n")
            f.write("-" * 40 + "\n")
            for org in self.found_data['organizations']:
                f.write(f"{org['name']}\n")
            
            f.write(f"\nRECENT ACTIVITIES ({len(self.found_data['events'])})\n")
            f.write("-" * 40 + "\n")
            for event in self.found_data['events'][:10]:
                f.write(f"{event['type']} - {event['repo']} - {event['created_at']}\n")
            
            f.write(f"\nGISTS ({len(self.found_data['gists'])})\n")
            f.write("-" * 40 + "\n")
            for gist in self.found_data['gists']:
                f.write(f"ID: {gist['id']}\n")
                f.write(f"Description: {gist['description']}\n")
                f.write(f"Files: {', '.join(gist['files'])}\n")
                f.write(f"Created: {gist['created_at']}\n")
                f.write("-" * 20 + "\n")
        
        self.log_success(f"Report saved to: {filename}")
        return filename

    def generate_report(self, username):
        print(f"\n" + "="*60)
        print(f"{Fore.MAGENTA}GITSCAN OSINT REPORT{Style.RESET_ALL}")
        print("="*60)
        
        print(f"\nTARGET: {username}")
        print(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\nFOUND EMAILS ({len(self.found_data['emails'])})")
        print("-" * 40)
        for email in self.found_data['emails']:
            print(f"  {Fore.GREEN}{email}{Style.RESET_ALL}")
        
        print(f"\nREPOSITORIES ({len(self.found_data['repos'])})")
        print("-" * 40)
        for repo in self.found_data['repos'][:5]:
            print(f"  {repo['name']}")
            print(f"     Stars: {repo['stars']} | Forks: {repo['forks']} | Language: {repo['language']}")
        
        print(f"\nORGANIZATIONS ({len(self.found_data['organizations'])})")
        print("-" * 40)
        for org in self.found_data['organizations']:
            print(f"  {org['name']}")
        
        print(f"\nRECENT ACTIVITIES ({len(self.found_data['events'])})")
        print("-" * 40)
        for event in self.found_data['events'][:5]:
            print(f"  {event['type']} - {event['repo']}")

    def run_scan(self, username, output_file=False):
        self.print_banner()
        
        self.log_info(f"Starting GitScan: {username}")
        print("="*50)
        
        all_repos = self.get_all_repos(username)
        
        if all_repos:
            self.scan_repositories(username, all_repos)
        
        self.get_user_info(username)
        self.get_user_events(username)
        self.get_user_organizations(username)
        self.get_user_gists(username)
        
        self.generate_report(username)
        
        if output_file:
            filename = self.save_report(username)
            return filename

def main():
    parser = argparse.ArgumentParser(description='GitScan OSINT Tool')
    parser.add_argument('-t', '--token', help='GitHub Personal Access Token')
    parser.add_argument('-u', '--username', help='Target GitHub username')
    parser.add_argument('-o', '--output', action='store_true', help='Save output to file')
    parser.add_argument('-th', '--threads', type=int, default=5, help='Number of threads (default: 5)')
    
    args = parser.parse_args()
    
    if not args.token:
        print(f"{Fore.MAGENTA}GitScan OSINT Tool v1.0{Style.RESET_ALL}")
        token = "<= Your Github API Token =>" #Github API Token goes here
    else:
        token = args.token
    
    if not args.username:
        username = input("Enter target GitHub username: ").strip()
    else:
        username = args.username
    
    if not token or not username:
        print(f"{Fore.RED}Error: Token and username required!{Style.RESET_ALL}")
        sys.exit(1)
    
    try:
        gitscan = GitScan(token, threads=args.threads)
        result_file = gitscan.run_scan(username, args.output)
        
        if args.output and result_file:
            print(f"\n{Fore.GREEN}Scan completed! Report saved as: {result_file}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.GREEN}Scan completed!{Style.RESET_ALL}")
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Scan interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
