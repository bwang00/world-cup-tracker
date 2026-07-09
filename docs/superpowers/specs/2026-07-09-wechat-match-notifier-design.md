# World Cup Match Notifier — Design Spec

## Overview

Add a match notification service to the existing world-cup-tracker project. The service runs on a Mac Mini as a background daemon, polls live match data, detects score changes, and pushes notifications to a WeCom (企业微信) group chat via webhook.

## Goals

- Real-time goal notifications pushed to WeCom group within ~60 seconds of the event
- Post-match summary with final score and all scorers
- Zero dependency on the Vercel-hosted website — the notifier operates independently
- Minimal maintenance burden — self-healing, auto-restart, tournament-aware lifecycle

## Non-Goals

- No user-facing web UI for notification preferences (single-user tool)
- No database — flat file state is sufficient for this use case
- No other notification channels (Telegram, email) in this iteration
- No modification to the existing Vercel website

## Architecture

```
worldcup26.ir API
       │
       ▼
┌──────────────────────┐          ┌─────────────────────┐
│  Mac Mini Notifier   │──POST──▶│  WeCom Group Webhook │
│  (polling daemon)    │          │  (group chat)        │
└──────────────────────┘          └─────────────────────┘
       │
       ▼
  ~/.wc-notifier/state.json
  (score snapshot)
```

The notifier is a standalone Python script managed by launchd on the Mac Mini (sto@192.168.192.148). It shares the same data source as the website (worldcup26.ir) but has no runtime coupling to it.

## Components

### 1. Polling Engine

Responsibilities: fetch match data at configured intervals, adapt polling frequency based on match activity.

Behavior:
- Default poll interval: 60 seconds
- Active match mode (any match currently in_progress): 30 seconds
- Idle mode (no matches today or all finished): 300 seconds
- Tournament ended (after configured end date): stop polling entirely

Data source: `GET https://worldcup26.ir/get/games` — returns all matches with scores and status.

### 2. Change Detector

Responsibilities: compare fresh API data against persisted state, identify actionable events.

Events detected:
- **Goal scored**: `new_score > old_score` for either team in an active match
- **Match finished**: status transitions from `in_progress` to `finished`

Anti-duplicate mechanism: each detected event is assigned a unique ID (e.g., `goal_home_2` meaning home team's 2nd goal) and recorded in the state file's `events_notified` array. Events already in this array are never re-notified.

Cold start behavior: when a match appears in API data but has no entry in state.json (e.g., after service restart), initialize the record with current scores but do NOT fire notifications. This prevents a restart during a 3-1 match from sending four spurious goal alerts.

### 3. Notification Sender

Responsibilities: format event data into human-readable messages, deliver via WeCom webhook.

Delivery mechanism: HTTP POST to the configured webhook URL with JSON body:
```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "<formatted message>"
  }
}
```

Message templates:

**Goal notification:**
```
⚽ 进球！
巴西 2 - 1 日本 (62')

🔥 Vinicius Jr.
📺 第73场 · 16强 · 北京时间 20:30
```

**Match finished summary:**
```
🏁 比赛结束
巴西 3 - 1 日本

⚽ 进球记录：
  • Vinicius Jr. 23', 62'
  • Endrick 78'
  • Mitoma 45'

📊 16强 · 巴西晋级8强
```

Note: scorer details depend on API data availability. If worldcup26.ir does not provide event-level detail (scorer names, minutes), the goal notification will omit the player name and show only the updated score line. The match summary will list goals as "Home × Away" without individual scorers.

### 4. State Persistence

File: `~/.wc-notifier/state.json`

Schema:
```json
{
  "last_check": "2026-07-09T20:30:00+08:00",
  "matches": {
    "<match_id>": {
      "home": "Brazil",
      "away": "Japan",
      "home_score": 2,
      "away_score": 1,
      "status": "in_progress",
      "events_notified": ["goal_home_1", "goal_away_1", "goal_home_2"]
    }
  }
}
```

The state file is updated atomically (write to temp file, then rename) to prevent corruption from crashes mid-write.

Critical invariant: state is only updated AFTER the corresponding notification has been successfully sent (HTTP 200 from webhook). If notification delivery fails, state remains unchanged and the event will be retried on the next poll cycle.

## File Organization

```
~/.wc-notifier/
├── notifier.py          # Main script (poll + detect + notify)
├── config.json          # Configuration (webhook URL, intervals, etc.)
├── state.json           # Score state snapshot (auto-generated)
└── notifier.log         # Runtime log
```

## Configuration

File: `~/.wc-notifier/config.json`

```json
{
  "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<YOUR_KEY>",
  "poll_interval_active": 30,
  "poll_interval_idle": 300,
  "poll_interval_default": 60,
  "timezone": "Asia/Shanghai",
  "tournament_end": "2026-07-20",
  "log_level": "INFO",
  "api_base_url": "https://worldcup26.ir/get"
}
```

## Process Management

Managed via macOS launchd as a user-level LaunchAgent.

Plist: `~/Library/LaunchAgents/com.wc-notifier.plist`

Key properties:
- `KeepAlive: true` — auto-restart on crash
- `RunAtLoad: true` — start on user login
- `StandardOutPath` / `StandardErrorPath` → `~/.wc-notifier/notifier.log`

Commands:
- Start: `launchctl load ~/Library/LaunchAgents/com.wc-notifier.plist`
- Stop: `launchctl unload ~/Library/LaunchAgents/com.wc-notifier.plist`
- Status: `launchctl list | grep wc-notifier`

## Error Handling

- **API unreachable**: log warning, sleep for current interval, retry next cycle. No notification sent.
- **Webhook delivery failure (non-200)**: log error, do NOT update state. Event will be retried next cycle.
- **Consecutive failures > 10**: attempt to send a "⚠️ 通知服务异常" alert to the webhook (best-effort self-diagnosis).
- **Malformed API response**: log error with response body snippet, skip cycle.
- **State file corruption**: if state.json is unreadable, log error and reinitialize (cold start behavior — no spurious notifications).

## Testing Strategy

- Unit tests for the change detector (mock API responses, verify correct events are identified)
- Integration test: run notifier with a mock HTTP server simulating worldcup26.ir, verify webhook receives expected messages
- Manual smoke test: configure webhook to a test WeCom group, simulate a score change in state.json, verify message appears

## Dependencies

- Python 3.x (available on Mac Mini)
- Standard library only: `urllib.request`, `json`, `time`, `logging`, `os`, `tempfile`
- No pip packages required

## Lifecycle

The service is meaningful only during the FIFA World Cup 2026 (June 11 – July 19, 2026). After `tournament_end` date, the polling loop exits cleanly. The launchd plist can be unloaded after the tournament.
