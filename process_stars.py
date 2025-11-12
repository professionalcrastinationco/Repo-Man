#!/usr/bin/env python3
"""
GitHub Stars to README automation
Fetches new starred repos, summarizes them with Gemini, appends to README
"""

import os
import json
import sys
from datetime import datetime, timezone
from github import Github
import google.generativeai as genai

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME')  # Your GitHub username
STATE_FILE = 'last_run.json'
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

def get_new_stars(github_client, username, since=None):
    """Fetch starred repos that are new since last run"""
    user = github_client.get_user(username)
    starred = user.get_starred()
    
    new_stars = []
    for repo in starred:
        # If we have a timestamp, only include repos starred after it
        if since and repo.starred_at:
            if repo.starred_at.replace(tzinfo=timezone.utc) <= since:
                continue
        new_stars.append(repo)
    
    return new_stars

def summarize_repo(gemini_model, repo):
    """Use Gemini to create a concise summary of the repo"""
    
    # Build context for Gemini
    context = f"""Repository: {repo.full_name}
Description: {repo.description or 'No description'}
Primary Language: {repo.language or 'Not specified'}
Stars: {repo.stargazers_count}
Topics: {', '.join(repo.get_topics()) if repo.get_topics() else 'None'}

README snippet:
{get_readme_snippet(repo)}

Create a 2-3 sentence summary of what this repo does and when someone would use it. 
Then list 2-4 primary use cases as bullet points.
Then list the tech stack/languages.
Keep it concise and practical."""

    try:
        response = gemini_model.generate_content(context)
        return response.text.strip()
    except Exception as e:
        print(f"Error summarizing {repo.full_name}: {e}")
        return f"Summary generation failed. {repo.description or 'No description available.'}"

def get_readme_snippet(repo):
    """Get first 500 chars of README if it exists"""
    try:
        readme = repo.get_readme()
        content = readme.decoded_content.decode('utf-8')
        return content[:500] + "..." if len(content) > 500 else content
    except:
        return "No README available"

def format_entry(repo, summary):
    """Format a repo entry for the README"""
    entry = f"\n\n---\n\n"
    entry += f"### [{repo.full_name}]({repo.html_url})\n\n"
    entry += f"⭐ {repo.stargazers_count} | "
    entry += f"🔤 {repo.language or 'Various'} | "
    entry += f"📅 Starred: {datetime.now().strftime('%Y-%m-%d')}\n\n"
    entry += f"{summary}\n"
    return entry

def update_readme(entries):
    """Append new entries to README"""
    
    # Read existing README or create new one
    if os.path.exists(README_FILE):
        with open(README_FILE, 'r') as f:
            content = f.read()
    else:
        content = """# GitHub Stars Library

Automatically generated summaries of repos I've starred.

---
"""
    
    # Append new entries
    with open(README_FILE, 'a') as f:
        for entry in entries:
            f.write(entry)
    
    return len(entries)

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
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Load last run state
    last_run = load_state()
    print(f"Last run: {last_run or 'Never'}")
    
    # Get new starred repos
    print(f"Fetching starred repos for {GITHUB_USERNAME}...")
    new_stars = get_new_stars(github_client, GITHUB_USERNAME, since=last_run)
    
    if not new_stars:
        print("No new starred repos found.")
        return
    
    print(f"Found {len(new_stars)} new starred repos")
    
    # Process each repo
    entries = []
    for i, repo in enumerate(new_stars, 1):
        print(f"Processing {i}/{len(new_stars)}: {repo.full_name}")
        summary = summarize_repo(gemini_model, repo)
        entry = format_entry(repo, summary)
        entries.append(entry)
    
    # Update README
    count = update_readme(entries)
    print(f"Added {count} entries to {README_FILE}")
    
    # Save state
    save_state()
    print("State saved. Done!")

if __name__ == "__main__":
    main()
