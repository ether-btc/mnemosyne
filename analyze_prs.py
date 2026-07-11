#!/usr/bin/env python3
"""Analyze all 5 PR JSON files and produce a structured summary."""
import json

prs = [425, 420, 405, 404, 401]

for num in prs:
    path = f"/tmp/pr{num}.json"
    with open(path) as f:
        data = json.load(f)
    
    print(f"{'='*80}")
    print(f"PR #{num}")
    print(f"{'='*80}")
    print(f"Title:    {data.get('title', 'N/A')}")
    print(f"Author:   {data['author'].get('login', 'N/A')}")
    print(f"Created:  {data.get('createdAt', 'N/A')}")
    print(f"Body (first 600 chars):")
    body = data.get('body', '')
    print(f"  {body[:600]}")
    print()
    
    # Files
    files = data.get('files', [])
    print(f"Files ({len(files)}):")
    for f in files:
        print(f"  - {f.get('path', '?')} ({f.get('additions',0)}+ / {f.get('deletions',0)}-)")
    
    # Additions/deletions totals
    print(f"Total changes: +{data.get('additions', 0)} / -{data.get('deletions', 0)}")
    
    # Comments
    comments = data.get('comments', [])
    print(f"Comments: {len(comments)} (by: {[c['author']['login'] for c in comments]})")
    
    # Reviews
    reviews = data.get('reviews', [])
    if isinstance(reviews, list):
        print(f"Reviews: {len(reviews)}")
        for r in reviews:
            state = r.get('state', 'N/A')
            author = r.get('author', {}).get('login', 'N/A')
            print(f"  - {author}: {state}")
        # Summarize review states
        states = [r.get('state','N/A') for r in reviews]
        if states:
            from collections import Counter
            print(f"  Review summary: {dict(Counter(states))}")
    else:
        print(f"Reviews: {reviews}")
    
    # Labels
    labels = data.get('labels', [])
    print(f"Labels: {[l.get('name', l) if isinstance(l, dict) else l for l in labels]}")
    
    # Merge state
    print(f"MergeStateStatus: {data.get('mergeStateStatus', 'N/A')}")
    
    # Referenced/fixed issues
    print(f"Referenced issues in body:", end="")
    import re
    issues = set()
    if body:
        for m in re.finditer(r'(?:Fixes|Closes|Resolves|fixes|closes|resolves|Related|related|Ref|ref)\s+(?:#(\d+)|(https?://[^\s\)]+issues/\d+))', body):
            issues.add(m.group(0))
        for m in re.finditer(r'#(\d+)', body):
            issues.add(f"#{m.group(1)}")
    if issues:
        for i in sorted(issues):
            print(f"  {i}")
    else:
        print("  (none found)")
    
    print()