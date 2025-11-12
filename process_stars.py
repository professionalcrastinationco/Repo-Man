#!/usr/bin/env python3
"""
GitHub Stars to README automation
Fetches new starred repos, categorizes and summarizes them with Gemini, generates organized README
"""

import os
import json
import sys
from datetime import datetime, timezone
from collections import defaultdict
from github import Github
import google.generativeai as genai

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME')
STATE_FILE = 'last_run.json'
REPOS_DB_FILE = 'repos_database.json'
README_FILE = 'README.md'

def load_state():
    """Load the last run timestamp"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            return datetime.fromisoformat(data['last_run'])
    return None

def save_state():
    """Save the current timestamp"""
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_run': datetime.now(timezone.utc).isoformat()}, f)

def load_repos_database():
    """Load existing repos database"""
    if os.path.exists(REPOS_DB_FILE):
        with open(REPOS_DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_repos_database(database):
    """Save repos database"""
    with open(REPOS_DB_FILE, 'w') as f:
        json.dump(database, f, indent=2)

def get_new_stars(github_client, username, since=None):
    """Fetch starred repos that are new since last run"""
    user = github_client.get_user(username)
    starred = user.get_starred()
    
    new_stars = []
    for repo in starred:
        if since and repo.starred_at:
            if repo.starred_at.replace(tzinfo=timezone.utc) <= since:
                continue
        new_stars.append(repo)
    
    return new_stars

def get_readme_snippet(repo):
    """Get first 800 chars of README if it exists"""
    try:
        readme = repo.get_readme()
        content = readme.decoded_content.decode('utf-8')
        return content[:800] + "..." if len(content) > 800 else content
    except:
        return "No README available"

def categorize_and_summarize_repo(gemini_model, repo):
    """Use Gemini to categorize and summarize the repo"""
    
    context = f"""Repository: {repo.full_name}
Description: {repo.description or 'No description'}
Primary Language: {repo.language or 'Not specified'}
Stars: {repo.stargazers_count}
Topics: {', '.join(repo.get_topics()) if repo.get_topics() else 'None'}

README snippet:
{get_readme_snippet(repo)}

Analyze this repository and provide a structured response in JSON format:

{{
  "main_category": "Choose ONE: AI & Machine Learning, Automation & Scripting, Blockchain & Web3, Browser Extensions, Content Management, Data & Analytics, Design & UI/UX, DevOps & Infrastructure, Education & Learning, Gaming & Graphics, Mobile Development, Other, Security & Privacy, Self Hosted, Smart Home, Tools & Utilities, Web Development",
  "subcategory": "A more specific category (e.g., 'Frontend Frameworks', 'Data Visualization', 'CI/CD Tools', etc.)",
  "summary": "2-3 sentence summary of what this does and when to use it",
  "use_cases": ["use case 1", "use case 2", "use case 3"],
  "tech_stack": ["language/framework 1", "language/framework 2"]
}}

Keep it practical and concise. Focus on what problem it solves."""

    try:
        response = gemini_model.generate_content(context)
        # Clean up markdown code blocks if present
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return data
    except Exception as e:
        print(f"Error analyzing {repo.full_name}: {e}")
        # Fallback structure
        return {
            "main_category": "Other",
            "subcategory": "Uncategorized",
            "summary": repo.description or "No description available.",
            "use_cases": ["General purpose"],
            "tech_stack": [repo.language] if repo.language else ["Various"]
        }

def generate_readme(repos_database):
    """Generate a complete organized README from the database"""
    
    # Organize repos by category
    organized = defaultdict(lambda: defaultdict(list))
    
    for repo_id, data in repos_database.items():
        main_cat = data['main_category']
        sub_cat = data['subcategory']
        organized[main_cat][sub_cat].append(data)
    
    # Sort categories and repos
    sorted_categories = sorted(organized.keys())
    
    # Build README content
    content = """# 🌟 GitHub Stars Library

> Automatically categorized and summarized repos I've starred. Updated daily.

**Total Repos:** {total} | **Last Updated:** {date}

---

## 📑 Table of Contents

{toc}

---

""".format(
        total=len(repos_database),
        date=datetime.now().strftime('%Y-%m-%d'),
        toc='\n'.join([f"- [{cat}](#{cat.lower().replace(' ', '-').replace('&', '')})" for cat in sorted_categories])
    )
    
    # Add each category
    for main_cat in sorted_categories:
        content += f"\n# {main_cat}\n\n"
        
        subcategories = sorted(organized[main_cat].keys())
        for sub_cat in subcategories:
            content += f"\n## {sub_cat}\n\n"
            
            repos = organized[main_cat][sub_cat]
            # Sort by stars
            repos.sort(key=lambda x: x['stars'], reverse=True)
            
            for repo in repos:
                content += f"### [{repo['name']}]({repo['url']})\n\n"
                content += f"⭐ {repo['stars']:,} | "
                content += f"🔤 {', '.join(repo['tech_stack'][:3])} | "
                content += f"📅 {repo['starred_date']}\n\n"
                content += f"{repo['summary']}\n\n"
                
                if repo['use_cases']:
                    content += "**Use Cases:**\n"
                    for uc in repo['use_cases'][:4]:
                        content += f"- {uc}\n"
                    content += "\n"
                
                content += "---\n\n"
    
    # Write README
    with open(README_FILE, 'w') as f:
        f.write(content)
    
    print(f"Generated {README_FILE} with {len(repos_database)} repos organized into {len(sorted_categories)} categories")

def main():
    # Verify environment variables
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(1)
    if not GITHUB_USERNAME:
        print("ERROR: GITHUB_USERNAME not set")
        sys.exit(1)
    
    # Initialize clients
    print("Initializing GitHub and Gemini clients...")
    github_client = Github(GITHUB_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    # Load existing database
    repos_db = load_repos_database()
    print(f"Loaded database with {len(repos_db)} existing repos")
    
    # Load last run state
    last_run = load_state()
    print(f"Last run: {last_run or 'Never'}")
    
    # Get new starred repos
    print(f"Fetching starred repos for {GITHUB_USERNAME}...")
    new_stars = get_new_stars(github_client, GITHUB_USERNAME, since=last_run)
    
    if not new_stars:
        print("No new starred repos found.")
        if repos_db:
            print("Regenerating README from existing database...")
            generate_readme(repos_db)
        return
    
    print(f"Found {len(new_stars)} new starred repos")
    
    # Process each new repo
    for i, repo in enumerate(new_stars, 1):
        print(f"Processing {i}/{len(new_stars)}: {repo.full_name}")
        
        # Skip if already in database
        if repo.full_name in repos_db:
            print(f"  Already processed, skipping...")
            continue
        
        analysis = categorize_and_summarize_repo(gemini_model, repo)
        
        repos_db[repo.full_name] = {
            'name': repo.full_name,
            'url': repo.html_url,
            'stars': repo.stargazers_count,
            'language': repo.language or 'Various',
            'starred_date': datetime.now().strftime('%Y-%m-%d'),
            'main_category': analysis['main_category'],
            'subcategory': analysis['subcategory'],
            'summary': analysis['summary'],
            'use_cases': analysis['use_cases'],
            'tech_stack': analysis['tech_stack']
        }
    
    # Save updated database
    save_repos_database(repos_db)
    print(f"Saved {len(new_stars)} new repos to database")
    
    # Generate new README
    generate_readme(repos_db)
    
    # Save state
    save_state()
    print("Done!")

if __name__ == "__main__":
    main()