#!/usr/bin/env python3
import requests
import json
import re
import sys
import time
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        self.scan_complete = False

    def print_banner(self):
        banner = f"""
        {Fore.MAGENTA}
  ⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣠⣤⣤⣶⣶⣶⣤⣤⣄⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
  ⠀⠀⠀⠀⠀⢀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⣄⠀⠀⠀⠀⠀⠀
  ⠀⠀⠀⣠⣶⣿⣿⡿⣿⣿⣿⡿⠋⠉⠀⠀⠉⠙⢿⣿⣿⡿⣿⣿⣷⣦⡀⠀⠀⠀
  ⠀ ⣼⣿⣿⠟⠁⢠⣿⣿⠏⠀⠀⢠⣤⣤⡀⠀⠀⢻⣿⣿⡀⠙⢿⣿⣿⣦⠀⠀
  ⣰⣿⣿⡟⠁⠀⠀⢸⣿⣿⠀⠀⠀⢿⣿⣿⡟⠀⠀⠈⣿⣿⡇⠀⠀⠙⣿⣿⣷⡄
  ⠈⠻⣿⣿⣦⣄⠀⠸⣿⣿⣆⠀⠀⠀⠉⠉⠀⠀⠀⣸⣿⣿⠃⢀⣤⣾⣿⣿⠟⠁
  ⠀⠀⠈⠻⣿⣿⣿⣶⣿⣿⣿⣦⣄⠀⠀⠀⢀⣠⣾⣿⣿⣿⣾⣿⣿⡿⠋⠁⠀⠀
⠀⠀  ⠀⠀⠀⠙⠻⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠛⠁⠀⠀⠀⠀⠀
⠀⠀⠀⠀  ⠀⠀⠀⠀⠈⠉⠛⠛⠿⠿⠿⠿⠿⠿⠛⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀
  ╔══════════════════════════════╗
  ║☆          GITSCAN v1.0      ~║
  ║       Enhanced OSINT Tool    ║
  ║~   Advanced Email Discovery ☆║
  ╚══════════════════════════════╝
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
            try:
                response = requests.get(url, headers=self.headers, timeout=30)
                
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
                    
                elif response.status_code == 403:
                    self.log_error("Rate limit exceeded. Waiting 60 seconds...")
                    time.sleep(60)
                    continue
                else:
                    self.log_error(f"Error retrieving page {page}: {response.status_code}")
                    break
                    
            except Exception as e:
                self.log_error(f"Exception on page {page}: {e}")
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
        
        return len(all_emails)

    def scan_repositories(self, username, repos):
        self.log_info(f"Analyzing {len(repos)} repositories with {self.threads} threads...")
        
        total_emails_found = 0
        completed_repos = 0
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_repo = {
                executor.submit(self.scan_single_repo, (username, repo, i+1, len(repos))): repo 
                for i, repo in enumerate(repos)
            }
            
            for future in as_completed(future_to_repo):
                try:
                    emails_found = future.result()
                    total_emails_found += emails_found
                    completed_repos += 1
                    self.log_info(f"Progress: {completed_repos}/{len(repos)} repositories completed")
                except Exception as e:
                    self.log_error(f"Repository scan failed: {e}")
        
        self.log_success(f"Repository scanning completed. Found {total_emails_found} emails total")
        return total_emails_found

    def scan_repo_commits(self, username, repo_name):
        emails_found = set()
        
        try:
            commits_url = f"https://api.github.com/repos/{username}/{repo_name}/commits"
            commits_response = requests.get(commits_url, headers=self.headers, timeout=30)
            
            if commits_response.status_code == 200:
                commits = commits_response.json()
                
                for commit in commits[:100]:
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
            search_response = requests.get(search_url, headers=self.headers, timeout=30)
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                
                for item in search_data.get('items', [])[:20]:
                    file_url = item['html_url']
                    raw_url = file_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                    
                    try:
                        content_response = requests.get(raw_url, timeout=30)
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

    def get_user_info(self, username):
        self.log_info("Retrieving user information...")
        
        url = f"https://api.github.com/users/{username}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
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
        except Exception as e:
            self.log_error(f"Error getting user info: {e}")
            return None

    def get_user_events(self, username):
        self.log_info("Analyzing recent activities...")
        
        url = f"https://api.github.com/users/{username}/events/public"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                events = response.json()
                self.log_success(f"Found {len(events)} public events")
                
                event_types = {}
                for event in events[:50]:
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
        except Exception as e:
            self.log_error(f"Error getting events: {e}")
            return []

    def get_user_organizations(self, username):
        self.log_info("Checking organizations...")
        
        url = f"https://api.github.com/users/{username}/orgs"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
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
        except Exception as e:
            self.log_error(f"Error getting organizations: {e}")
            return []

    def get_user_gists(self, username):
        self.log_info("Scanning gists...")
        
        url = f"https://api.github.com/users/{username}/gists"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                gists = response.json()
                self.log_success(f"Found {len(gists)} gists")
                
                for gist in gists[:10]:
                    gist_info = {
                        'id': gist['id'],
                        'description': gist.get('description', 'N/A'),
                        'files': list(gist['files'].keys()),
                        'created_at': gist['created_at']
                    }
                    self.found_data['gists'].append(gist_info)
                
                return gists
            else:
                self.log_warning("Failed to retrieve gists")
                return []
        except Exception as e:
            self.log_error(f"Error getting gists: {e}")
            return []

    def is_personal_email(self, email):
         corporate_domains = [
          'gmail.com','googlemail.com','outlook.com','hotmail.com','live.com','msn.com','yahoo.com','ymail.com','rocketmail.com','icloud.com','me.com','mac.com','protonmail.com','proton.me','pm.me','protonmail.ch','protonmail.at','tutanota.com','tuta.com','tuta.io','tutanota.de','keinspam.de','tutamail.com','gmx.net','gmx.de','gmx.at','gmx.ch','gmx.us','mail.gmx.net','web.de','freenet.de','t-online.de','arcor.de','1und1.de','unitybox.de','unitymail.de','ionos.de','ionos.com','strato.de','posteo.de','mailbox.org','posteo.net','posteo.ch','posteo.eu','zoho.com','zoho.eu','zohomail.com','fastmail.com','fastmail.fm','fastmail.net','fastmail.org','runbox.com','runbox.no','disroot.org','autistici.org','riseup.net','systemli.org','cock.li','airmail.cc','hey.com','skiff.com','skiff.org','migadu.com','mxroute.com','mail.com','email.com','inbox.com','europe.com','usa.com','yandex.com','yandex.ru','yandex.by','yandex.kz','yandex.ua','mail.ru','bk.ru','inbox.ru','list.ru','vipmail.ru','rambler.ru','seznam.cz','email.cz','centrum.cz','volny.cz','wp.pl','onet.pl','poczta.onet.pl','interia.pl','poczta.fm','op.pl','orange.fr','free.fr','laposte.net','sfr.fr','bouyguestelecom.fr','neuf.fr','wanadoo.fr','libero.it','alice.it','virgilio.it','tim.it','tiscali.it','gmx.fr','mail.fr','aol.com','aol.de','aol.fr','aol.co.uk','btinternet.com','btopenworld.com','ntlworld.com','blueyonder.co.uk','talktalk.net','sky.com','virginmedia.com','comcast.net','verizon.net','att.net','sbcglobal.net','bellsouth.net','cox.net','charter.net','earthlink.net','qq.com','163.com','126.com','sina.com','sohu.com','naver.com','daum.net','hanmail.net','nate.com','hotmail.co.uk','hotmail.de','hotmail.fr','hotmail.it','hotmail.es','hotmail.be','live.co.uk','live.de','live.fr','live.it','gmx.at','aon.at','chello.at','magnet.at','hispeed.ch','bluewin.ch','swissonline.ch','sunrise.ch','gmx.ch','hotmail.ch','swisscom.ch','cablecom.ch','green.ch','solnet.ch','uol.com.br','bol.com.br','ig.com.br','terra.com.br','r7.com','zipmail.com.br','globomail.com','oi.com.br','hotmail.com.br','live.com.br','outlook.com.br','gmx.com','gmx.co.uk','gmx.es','gmx.it','gmx.fr','gmx.pt','gmx.us','mail.com','email.com','e-mail.com','usa.com','europe.com','asia.com','africa.com','inbox.com','safe-mail.net','hushmail.com','keemail.me','mail.ru','list.ru','bk.ru','inbox.ru','yandex.com','ya.ru','yandex.ru','mail.yandex','yandex.ua','yandex.by','yandex.kz','rambler.ru','lenta.ru','autorambler.ru','myrambler.ru','ro.ru','r0.ru','pochta.ru','hotbox.ru','nm.ru','mail15.com','mail.ru','go.ru','ok.ru','inbox.lv','mail.lv','apollo.lv','inbox.lt','mail.ee','hot.ee','one.lt','one.ee','freemail.hu','citromail.hu','vipmail.hu','azet.sk','zoznam.sk','poczta.pl','poczta.fm','interia.eu','poczta.interia.pl','tlen.pl','autograf.pl','vp.pl','wp.pl','o2.pl','gazeta.pl','abv.bg','dir.bg','mail.bg','hotmail.gr','yahoo.gr','otenet.gr','forthnet.gr','vodafone.gr','cosmote.gr','wind.gr','hotmail.es','yahoo.es','terra.es','ono.com','wanadoo.es','telefonica.net','jazztel.es','ya.com','eresmas.com','hotmail.it','yahoo.it','tin.it','katamail.com','inwind.it','supereva.it','email.it','hotmail.nl','yahoo.nl','planet.nl','kpnmail.nl','hetnet.nl','freeler.nl','home.nl','xs4all.nl','chello.nl','quicknet.nl','hotmail.be','yahoo.be','skynet.be','telenet.be','proximus.be','scarlet.be','base.be','hotmail.se','yahoo.se','spray.se','telia.com','bredband.net','comhem.se','hotmail.no','yahoo.no','online.no','start.no','c2i.net','hotmail.dk','yahoo.dk','jubii.dk','sol.dk','stofanet.dk','hotmail.fi','yahoo.fi','luukku.com','elisa.net','kolumbus.fi','suomi24.fi','hotmail.pt','yahoo.pt','sapo.pt','clix.pt','netcabo.pt','telepac.pt','hotmail.com.ar','yahoo.com.ar','fibertel.com.ar','speedy.com.ar','ciudad.com.ar','arnet.com.ar','hotmail.com.mx','yahoo.com.mx','prodigy.net.mx','live.com.mx','hotmail.cl','yahoo.cl','terra.cl','entel.cl','vtr.net','manquehue.net','hotmail.com.co','yahoo.com.co','une.net.co','etb.net.co','hotmail.com.ve','yahoo.com.ve','cantv.net','hotmail.com.br','yahoo.com.br','uol.com.br','bol.com.br','ig.com.br','terra.com.br','oi.com.br','r7.com','globomail.com','zipmail.com.br','hotmail.co.za','yahoo.co.za','mweb.co.za','telkomsa.net','vodamail.co.za','hotmail.com.au','yahoo.com.au','bigpond.com','bigpond.net.au','optusnet.com.au','iinet.net.au','westnet.com.au','hotmail.co.nz','yahoo.co.nz','xtra.co.nz','clear.net.nz','paradise.net.nz','hotmail.co.in','yahoo.co.in','rediffmail.com','indiatimes.com','vsnl.net','sify.com','hotmail.co.jp','yahoo.co.jp','nifty.com','ocn.ne.jp','hotmail.co.kr','yahoo.co.kr','hanmail.net','daum.net','nate.com','hotmail.com.tw','yahoo.com.tw','seed.net.tw','hotmail.com.hk','yahoo.com.hk','netvigator.com','pchome.com.tw','hotmail.com.sg','yahoo.com.sg','singnet.com.sg','pacific.net.sg','hotmail.com.my','yahoo.com.my','tm.net.my','streamyx.com','hotmail.co.th','yahoo.co.th','cscoms.com','hotmail.com.ph','yahoo.com.ph','pldt.net','smart.com.ph','hotmail.com.tr','yahoo.com.tr','superposta.com','mynet.com','hotmail.com.eg','yahoo.com.eg','link.net','tedata.net','hotmail.com.sa','yahoo.com.sa','nesma.net.sa','hotmail.com.pk','yahoo.com.pk','cyber.net.pk','hotmail.co.id','yahoo.co.id','centrin.net.id','telkom.net','hotmail.com.vn','yahoo.com.vn','vnpt.vn','fpt.vn','hotmail.ru','yandex.ru','mail.ru','rambler.ru','pochta.ru','ngs.ru','hotmail.ua','meta.ua','ukr.net','bigmir.net','i.ua','hotmail.kz','mail.kz','yandex.kz','hotmail.by','tut.by','mail.by','yandex.by','hotmail.az','mail.az','yandex.az','hotmail.ge','mail.ge','yandex.ge','hotmail.am','mail.am','yandex.am','hotmail.tm','mail.tm','yandex.tm','hotmail.kg','mail.kg','yandex.kg','hotmail.tj','mail.tj','yandex.tj','hotmail.uz','mail.uz','yandex.uz','hotmail.md','mail.md','yandex.md','hotmail.al','mail.al','yandex.al','hotmail.ba','mail.ba','yandex.ba','hotmail.hr','mail.hr','yandex.hr','hotmail.si','mail.si','yandex.si','hotmail.rs','mail.rs','yandex.rs','hotmail.mk','mail.mk','yandex.mk','hotmail.me','mail.me','yandex.me','hotmail.lt','mail.lt','yandex.lt','hotmail.lv','mail.lv','yandex.lv','hotmail.ee','mail.ee','yandex.ee','hotmail.is','mail.is','yandex.is','hotmail.gr','mail.gr','yandex.gr','hotmail.ro','mail.ro','yandex.ro','hotmail.bg','mail.bg','yandex.bg','hotmail.sk','mail.sk','yandex.sk','hotmail.cz','mail.cz','yandex.cz','hotmail.hu','mail.hu','yandex.hu','hotmail.pl','mail.pl','yandex.pl','hotmail.at','mail.at','yandex.at','hotmail.ch','mail.ch','yandex.ch','hotmail.de','mail.de','yandex.de','hotmail.fr','mail.fr','yandex.fr','hotmail.it','mail.it','yandex.it','hotmail.es','mail.es','yandex.es','hotmail.pt','mail.pt','yandex.pt','hotmail.nl','mail.nl','yandex.nl','hotmail.be','mail.be','yandex.be','hotmail.se','mail.se','yandex.se','hotmail.no','mail.no','yandex.no','hotmail.dk','mail.dk','yandex.dk','hotmail.fi','mail.fi','yandex.fi','hotmail.is','mail.is','yandex.is','hotmail.ie','mail.ie','yandex.ie','hotmail.co.uk','mail.co.uk','yandex.co.uk','hotmail.com.au','mail.com.au','yandex.com.au','hotmail.co.nz','mail.co.nz','yandex.co.nz','hotmail.co.za','mail.co.za','yandex.co.za','hotmail.com','mail.com','yandex.com'
          ] 
         domain = email.split('@')[-1].lower()
         return domain in corporate_domains

    def save_report(self, username):
        filename = f"{username}_report.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("GITSCAN v1.0  OSINT REPORT\n")
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
            for email in sorted(self.found_data['emails']):
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
            for event in self.found_data['events'][:15]:
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
        print(f"{Fore.MAGENTA}GITSCAN v1.0 OSINT REPORT{Style.RESET_ALL}")
        print("="*60)
        
        print(f"\nTARGET: {username}")
        print(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\nFOUND EMAILS ({len(self.found_data['emails'])})")
        print("-" * 40)
        for email in sorted(self.found_data['emails']):
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
        
        self.log_info(f"Starting GitScan v1.0: {username}")
        print("="*50)
        
        start_time = time.time()
        
        all_repos = self.get_all_repos(username)
        
        if all_repos:
            self.scan_repositories(username, all_repos)
        
        self.get_user_info(username)
        self.get_user_events(username)
        self.get_user_organizations(username)
        self.get_user_gists(username)
        
        elapsed_time = time.time() - start_time
        
        self.log_success(f"Scan completed in {elapsed_time:.2f} seconds")
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
        print(f"{Fore.MAGENTA}GitScan  OSINT Tool v1.0{Style.RESET_ALL}")
        token = "<TOKEN>" #Your Github API token goes here (if u dont want to use the -t argument
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
