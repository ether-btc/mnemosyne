#!/usr/bin/env python3
"""Post a Mnemosyne update tweet via clix auth tokens directly."""
import json, os, sys, urllib.request, urllib.error

auth_path = os.path.expanduser("~/.config/clix/auth.json")
with open(auth_path) as f:
    auth = json.load(f)

acct = auth["accounts"]["mnemosyne"]
auth_token = acct["auth_token"]
ct0 = acct["ct0"]
COOKIE = f"auth_token={auth_token}; ct0={ct0}"
BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

text = "Mnemosyne v3.11.1 is out! cross-session env var, sync_turn diagnostics, pure-ASGI auth fix, namespace fix, MCP veracity fix, and more. github.com/AxDSan/mnemosyne"

print(f"Text length: {len(text)} chars")

qid = "R5EPiGHgSqbTYFyozd-gFw"

def headers():
    return {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
        "authorization": f"Bearer {BEARER}",
        "x-csrf-token": ct0,
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
        "origin": "https://x.com",
        "referer": "https://x.com/",
        "cookie": COOKIE,
    }

variables = {"tweet_text": text}
features = {
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "responsive_web_twitter_blue_verified_badge_is_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

body = json.dumps({"variables": variables, "features": features, "queryId": qid}).encode()
print(f"Body size: {len(body)} bytes")
url = f"https://x.com/i/api/graphql/{qid}/CreateTweet"

req = urllib.request.Request(url, data=body, headers=headers(), method="POST")
try:
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode())
    print(json.dumps(result, indent=2)[:500])
    if "errors" in result:
        sys.exit(1)
    tid = result["data"]["create_tweet"]["tweet_results"]["result"]["rest_id"]
    print(f"Posted! https://x.com/mnemosyne_oss/status/{tid}")
except urllib.error.HTTPError as e:
    body = e.read().decode()[:1000]
    print(f"HTTP {e.code}: {body}")
    sys.exit(1)
except Exception as e:
    print(f"Failed: {e}")
    sys.exit(1)