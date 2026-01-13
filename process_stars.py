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

def get_new_stars(github_client, username, existing_repos):
    """Fetch starred repos that aren't already in the database"""
    user = github_client.get_user(username)
    starred = user.get_starred()
    
    new_stars = []
    for repo in starred:
        # Skip if already in database
        if repo.full_name not in existing_repos:
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

You must respond with ONLY a valid JSON object, nothing else. No markdown, no code blocks, no explanations.

Analyze this repository and respond with this exact JSON structure:

{{
  "main_category": "Choose ONE from this exact list: AI Agents & Assistants, AI Infrastructure, Automation, Data & Analytics, Design & Assets, Developer Tools, Home Automation, Self-Hosted Apps, Web Development",
  "subcategory": "Choose the most appropriate subcategory based on main_category:
    - AI Agents & Assistants: Agent Frameworks, Claude Ecosystem, LLM Applications, Memory & Context, MCP Servers, Multi-Agent Systems
    - AI Infrastructure: Generative AI, LLM Resources, Model Serving, NLP & Speech, Training & Fine-tuning
    - Automation: Browser Automation, Creative Scripts, Web Scraping, Workflow Platforms
    - Data & Analytics: Data Apps, Dashboards, Data Processing, Finance & Quant
    - Design & Assets: Animations & Effects, Design Resources, Icon Libraries
    - Developer Tools: API Resources, Awesome Lists, CLI Utilities, Dev Methodology, JSON & Data Tools
    - Home Automation: HA Integrations, HA Resources, Smart Home Apps
    - Self-Hosted Apps: Dashboards & Startpages, Databases & Backends, Media Tools, Notes & Knowledge
    - Web Development: Component Libraries, Frontend Frameworks, Full-Stack Python, Starter Templates, Web Services",
  "summary": "2-3 sentence summary of what this does and when to use it",
  "use_cases": ["use case 1", "use case 2", "use case 3"],
  "tech_stack": ["language/framework 1", "language/framework 2"]
}}

CRITICAL: Your response must be ONLY the JSON object. Do not include ```json or ``` or any other text. Just the JSON."""

    try:
        response = gemini_model.generate_content(context)
        text = response.text.strip()
        
        # Aggressive markdown cleanup
        text = text.replace('```json', '').replace('```', '')
        text = text.strip()
        
        # Find JSON object if there's extra text
        if '{' in text and '}' in text:
            start = text.index('{')
            end = text.rindex('}') + 1
            text = text[start:end]
        
        print(f"  Raw response length: {len(text)} chars")
        
        data = json.loads(text)
        
        # Validate required fields
        required = ['main_category', 'subcategory', 'summary', 'use_cases', 'tech_stack']
        if not all(key in data for key in required):
            raise ValueError(f"Missing required fields. Got: {data.keys()}")
        
        print(f"  ✓ Categorized as: {data['main_category']} > {data['subcategory']}")
        return data
        
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parsing failed: {e}")
        print(f"  Response preview: {text[:200] if 'text' in locals() else 'No response'}")
    except Exception as e:
        print(f"  ✗ Error analyzing: {e}")
    
    # Fallback - but print warning
    print(f"  ⚠ Using fallback categorization")
    return {
        "main_category": "Developer Tools",
        "subcategory": "Awesome Lists",
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
    
    # Build detailed TOC
    toc = "## 📑 Table of Contents\n\n"
    for main_cat in sorted_categories:
        # Category header
        toc += f"* **{main_cat}**\n"
        
        # Get all repos in this category (across all subcategories)
        cat_repos = []
        for sub_cat in organized[main_cat].values():
            cat_repos.extend(sub_cat)
        
        # Sort by stars and show top repos
        cat_repos.sort(key=lambda x: x['stars'], reverse=True)
        for repo in cat_repos[:10]:  # Show top 10 per category in TOC
            # Generate short summary (first 1-3 words from summary or use first use case)
            short = repo['use_cases'][0] if repo['use_cases'] else repo['summary']
            # Take first few words
            words = short.split()[:3]
            short_desc = ' '.join(words)
            repo_name = repo['name'].split('/')[-1]  # Just the repo name, not owner
            toc += f"   * [{repo_name}](#{repo['name'].lower().replace('/', '').replace('_', '-').replace('.', '')}) ({short_desc})\n"
        
        if len(cat_repos) > 10:
            toc += f"   * *...and {len(cat_repos) - 10} more*\n"
        toc += "\n"
    
    # Build README content
    content = f"""# 🌟 GitHub Stars Library

> Automatically categorized and summarized repos I've starred. Updated daily.

**Total Repos:** {len(repos_database)} | **Last Updated:** {datetime.now().strftime('%Y-%m-%d')}

---

{toc}

---

"""
    
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
    gemini_model = genai.GenerativeModel('models/gemini-flash-latest')
    
    # Load existing database
    repos_db = load_repos_database()
    print(f"Loaded database with {len(repos_db)} existing repos")
    
    # Load last run state
    last_run = load_state()
    print(f"Last run: {last_run or 'Never'}")
    
    # Get new starred repos
    print(f"Fetching starred repos for {GITHUB_USERNAME}...")
    new_stars = get_new_stars(github_client, GITHUB_USERNAME, repos_db)
    
    if not new_stars:
        print("No new starred repos found. Nothing to do.")
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