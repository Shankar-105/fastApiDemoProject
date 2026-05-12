# 🌟 Features — Everything Inside Social Media Api

> A deep dive into every feature powering this backend. Nothing skipped.

---

## 📑 Table of Contents

| Section | What It Covers |
|---------|---------------|
| [Async & Non-Blocking Architecture](#-async--non-blocking-architecture) | Event-loop design, thread-pool offloading, async DB & cache |
| [Concurrency Hardening & Database Design](#-concurrency-hardening--database-design) | 5 production-safe techniques and schema choices that prevent race conditions, stale writes, and counter drift |
| [Authentication & Security](#-authentication--security) | JWT with expiry verification, bcrypt, token blacklist, logout, OTP |
| [Refresh Token Rotation](#-refresh-token-rotation) | Opaque refresh tokens, family-based revocation, silent re-auth |
| [Rate Limiting](#-rate-limiting) | IP-based & user-based throttling, configurable per endpoint |
| [Notifications](#-notifications) | Real-time push via Redis Pub/Sub + WebSocket, persistent storage |
| [User Profiles](#-user-profiles) | Bio, nickname, profile picture, update flow |
| [Follow / Unfollow System](#-follow--unfollow-system) | Follow, unfollow, remove follower, counts |
| [Posts](#-posts) | CRUD, media uploads, views, hashtags |
| [Comments](#-comments) | Create, edit, delete, like comments |
| [Voting / Likes System](#-voting--likes-system) | Like/dislike toggle, vote stats, analytics |
| [Feed System](#-feed-system) | Home feed, explore feed, pagination |
| [Saved Posts](#-saved-posts) | Save, unsave, and retrieve saved posts |
| [Search](#-search) | User search, hashtag search, ordering |
| [Password Management](#-password-management) | Change, forgot, reset via OTP |
| [Real-Time Chat (WebSockets)](#-real-time-chat-websockets) | Direct messages, media, typing, reactions, read receipts |
| [Message Controls](#-message-controls) | Reply, edit, delete for me, delete for everyone, clear chat |
| [Post Sharing into DMs](#-post-sharing-into-dms) | Share posts, react to shares, reply to shares |
| [Background Jobs (Celery + RabbitMQ)](#-background-jobs-celery--rabbitmq) | Message queues, retries, scheduled cleanup, failure isolation |
| [Redis Caching & Token Blacklisting](#-redis-caching--token-blacklisting) | Response caching across 11+ endpoints, pattern-based invalidation, secure logout |
| [Media & File Management](#-media--file-management) | Profile pics, post media, chat media, static serving |
| [Database & Migrations](#-database--migrations) | PostgreSQL, SQLAlchemy 2.0, Alembic, async sessions |
| [DevOps & Docker](#-devops--docker) | Docker Compose, multi-service stack, volumes, auto-restart |
| [API Documentation](#-api-documentation) | Swagger UI, ReDoc, Pydantic schemas |
| [API Versioning](#-api-versioning) | Semantic versioning (v1, v2) to prevent breaking changes for clients |
| [Testing](#-testing) | Pytest, isolated test DB, 50+ integration tests |
| [Observability and Load Testing](#-observability-and-load-testing) | OpenTelemetry, Prometheus, Grafana, and k6 traffic simulation |
---

## ⚡ Async & Non-Blocking Architecture

The entire backend is built on an **async-first** philosophy — from the first request to the last database query, nothing blocks the event loop.

- **Async route handlers** — every FastAPI route is defined with `async def`, allowing the server to handle thousands of concurrent connections on a single process.
- **Async database sessions** — powered by `asyncpg` + SQLAlchemy's `AsyncSession`, all database reads and writes are non-blocking. No request waits idle while another query finishes.
- **Thread-pool offloading for CPU-bound work** — operations like `bcrypt` password hashing/verification and `JWT` encode/decode are CPU-intensive. These are offloaded via `asyncio.to_thread()` so the event loop stays free while cryptographic operations crunch in the background.
- **Async Redis operations** — all cache reads, writes, and deletions go through `redis.asyncio`, keeping the caching layer fully non-blocking.
- **Async email delivery** — OTP emails are sent via `fastapi-mail` with `aiosmtplib` under the hood — no synchronous SMTP calls blocking the server.
- **Async WebSocket management** — the `ConnectionManager` tracks active sockets, injects peer presence metadata, and delivers typing/message events without blocking any other connection.
- **Zero sync bottlenecks** — even utility functions like OTP generation, cache invalidation, and expired OTP cleanup are fully async.

> **What this means in practice:** The server can handle hundreds of simultaneous REST requests, WebSocket connections, file uploads, and database queries — all on a single worker process — without any request waiting on another.

---

## 🧱 Concurrency Hardening & Database Design

Built for real traffic, not like a simple crud app. I hardened critical write paths with a layered strategy that keeps data correct even under high concurrent request load and also pushed schema rules down into PostgreSQL where they belong.

- 🧱 **Database-Owned Counters** — hot counts are synchronized by database triggers or single-statement SQL updates, so the app no longer depends on Python-side read-modify-write loops.
- 🛡️ **Conflict-Safe Inserts** — `ON CONFLICT DO NOTHING` protects follow/vote/save/reaction flows from duplicate-race errors.
- 🔍 **Optimistic Locking** — `version_id_col` detects stale writes and prevents silent overwrite of profile/auth changes.
- 🔒 **Pessimistic Locking** — `SELECT ... FOR UPDATE` serializes short critical sections when read-validate-write must be deterministic.
- 🔁 **Transient Retry** — bounded retry with jitter recovers from PostgreSQL deadlock/serialization aborts (`40P01`, `40001`) without hiding real business errors.
- 🧩 **Database Design Guardrails** — check constraints, partial indexes, trigram search indexes, and hashed auth secrets keep the schema resilient even when code paths grow.

### Why this makes the app better

- ✅ More consistent counters and state transitions under heavy load
- ✅ Safer profile/auth updates across multi-device sessions
- ✅ Fewer race-condition bugs in chat edit/delete/reply and read-state flows
- ✅ Less counter drift because the database owns more of the derived state
- ✅ Better resilience during contention spikes

### Current database design choices in the app

- Derived counters for posts, comments, reactions, followers, and views are synchronized in PostgreSQL, not by hand in Python.
- Search uses PostgreSQL trigram indexes for username and hashtag matching.
- Refresh tokens and OTPs are stored hashed at rest.
- Schema constraints reject invalid counters, invalid media types, and duplicate relational states before they reach application code.

---

## 🔐 Authentication & Security

- **JWT access tokens** with configurable expiry time — generated using HMAC-SHA256 via `python-jose`
- **Email verification on signup** — newly registered users receive an OTP by email and must verify before first login
- **Explicit JWT expiry verification** — every token decode checks the `expTime` claim against `datetime.now(timezone.utc)`; expired tokens are rejected immediately with a clear error
- **UTC-aware timestamps everywhere** — token creation, expiry checks, and blacklist TTL calculations all use `timezone.utc` to prevent clock-skew issues
- **Secure password hashing** using `bcrypt` with automatic salt generation
- **Token-based logout** — on logout, the JWT is added to a Redis blacklist with its remaining TTL, and **all refresh tokens** for that user are revoked (forces re-login on every device)
- **Blacklist check on every request** — every protected endpoint verifies the token hasn't been blacklisted before processing
- **OAuth2PasswordBearer** scheme — extracts the JWT from the `Authorization: Bearer <token>` header automatically
- **User enumeration prevention** — login returns a generic `"Invalid credentials"` message with `401` for both wrong username and wrong password; forgot-password returns a generic success message regardless of whether the email exists
- **Unverified account login block** — login returns `403` for users who have not completed email verification
- **Form-based login** — uses FastAPI's built-in `OAuth2PasswordRequestForm` for standards-compliant login
- **CORS middleware** — Cross-Origin Resource Sharing enabled for frontend integration

---

## 🔄 Refresh Token Rotation

A production-grade refresh token system with **family-based revocation** for maximum security.

- **Opaque refresh tokens** — generated via `secrets.token_urlsafe(32)`, not JWTs. Stored securely in PostgreSQL as SHA-256 digests
- **Token rotation on every refresh** — calling `POST /v1/auth/refresh-token` issues a new access + refresh token pair and immediately revokes the old refresh token
- **Family-based revocation** — each login session gets a unique `family_id` (UUID). If a revoked token is reused (replay attack), the **entire family** is revoked, forcing re-login on all devices in that session
- **Configurable expiry** — refresh tokens expire after `REFRESH_TOKEN_EXPIRE_DAYS` (default: 7 days), set via `.env`
- **Logout nukes all tokens** — `POST /v1/auth/logout` blacklists the access token and revokes every refresh token for that user across all devices
- **Password change revokes sessions** — changing your password automatically revokes all refresh tokens, preventing stale sessions from silently refreshing

---

## 🛡️ Rate Limiting

IP-based and user-based throttling to protect against abuse, brute-force attacks, and spam.

- **Two strategies:**
  - **IP-based** — throttles by client IP address (login, signup, forgot-password, reset-password, refresh)
  - **User-based** — throttles by authenticated user ID (change-password OTP, authenticated reset-password, create comment, create post, follow)
- **Redis-backed counters** — atomic `INCR` + `EXPIRE` in Redis; counters survive app restarts
- **Configurable per endpoint** via `.env`:
  | Endpoint | Default Limit | Window |
  |----------|--------------|--------|
  | Login | 5 requests | 5 min |
  | Signup | 3 requests | 1 hour |
  | Forgot Password | 3 requests | 1 hour |
  | Reset Password | 5 requests | 5 min |
  | Refresh Token | 10 requests | 1 min |
  | Change Password OTP | 3 requests | 1 hour |
  | Create Comment | 10 requests | 1 min |
  | Create Post | 5 requests | 1 min |
  | Follow | 20 requests | 1 min |
- **Proper 429 responses** — returns `HTTP 429 Too Many Requests` with a `Retry-After` header indicating when the client can retry
- **Graceful degradation** — if Redis is down, rate limiting is bypassed rather than breaking the API

---

## 🔔 Notifications

Real-time notification system with persistent storage and live delivery.

- **Notification types:** `like`, `comment`, `follow` — generated automatically when a user interacts with your content
- **Persistent storage** — all notifications saved in a dedicated `notifications` table with `owner_id`, `actor_id`, `type`, `entity_id`, `entity_type`, `text`, `is_read`, and `created_at`
- **Real-time delivery** — if the target user has an active WebSocket connection, the notification is pushed instantly through the connection manager
- **REST endpoints:**
  - `GET /v1/users/me/notifications` — paginated notification list (cached 20s in Redis)
  - `GET /v1/users/me/notifications/unread-count` — unread badge count (cached 20s)
  - `PATCH /v1/users/me/notifications/read` — mark all as read (invalidates caches)
- **Automatic cache invalidation** — creating a new notification clears the target user's notification caches so they see fresh data on next request
- **No self-notifications** — liking your own post or following yourself doesn't generate a notification

---

## 🚚 Background Jobs (Celery + RabbitMQ)

The app now pushes slow or repeatable work into a queue instead of doing it in the request path.

- **Task queue architecture** — FastAPI submits work with `.delay()`, RabbitMQ stores the message, and Celery workers execute it later.
- **RabbitMQ broker** — durable AMQP broker that keeps tasks safe until a worker is ready.
- **Celery workers** — long-running background processes that send emails, clean up OTPs, and persist notifications.
- **Celery Beat** — scheduler for periodic jobs such as hourly OTP cleanup.
- **Flower monitoring** — web dashboard at port `5555` for active tasks, failures, worker health, and queue inspection.
- **Result backend** — Redis DB 1 keeps task state and results so the app can query status later.
- **Automatic retries** — tasks use exponential backoff when transient errors happen.
- **Dead-letter queue** — tasks that exhaust retries can be isolated for later inspection instead of vanishing.
- **Operational visibility** — task IDs, worker state, and queue depth can be tracked from both Flower and the API.
- **Failure isolation** — background work no longer blocks signups, logins, or comment creation when a downstream service is slow.
- **Use cases** — OTP emails, verification emails, notification persistence, and hourly maintenance jobs.
- **Safer request handling** — HTTP responses return immediately while background work continues independently.

---

## 👤 User Profiles

- **Registration** with username (unique, 3–50 chars), password (6–72 chars, bcrypt-hashed), optional nickname, and required email (OTP verified)
- **Profile fields** — username, nickname, bio (up to 500 chars), email, profile picture
- **Profile picture upload** — accepts JPEG, PNG, and GIF files via `multipart/form-data`
- **Profile picture removal** — deletes the file from disk and clears the database reference
- **Partial updates** via `PATCH` — update any combination of username, bio, and profile picture in a single request
- **Username uniqueness check** — prevents duplicates when updating
- **View any user's profile** — includes `is_following` status for the current user
- **All users listing** — public endpoint to browse all registered users

---

## 🔗 Follow / Unfollow System

- **Many-to-many relationship** — implemented via a dedicated `connections` association table
- **Follow a user** — with guards against self-following and duplicate follows
- **Unfollow a user** — removes the connection, updates counts instantly
- **Remove a follower** — you can kick someone off your followers list
- **Follower/following lists** — paginated lists with user info and `is_following` status for each entry
- **Live counts** — `followers_count` and `following_count` are maintained in the database and reconciled from the `connections` table
- **Cascading deletes** — if a user is deleted, all their follow connections are cleaned up automatically

---

## 📝 Posts

- **Full CRUD** — create, read, update, delete posts
- **Rich content** — each post has a title, content body, optional media (image or video), and optional hashtags
- **Media uploads** — supports JPEG, PNG images and MP4 video files via `multipart/form-data`
- **Unique filenames** — uploaded media gets a UUID-based filename to prevent collisions
- **File cleanup on delete** — when a post is deleted, its media file is removed from disk
- **View counter** — tracks unique views per user per post using a dedicated `PostView` table and a database-synced post view count
- **Like/dislike counts** — maintained directly on the post and synchronized from the `votes` table for fast retrieval
- **Comment count** — synchronized from comment inserts/deletes so it stays aligned with the `comments` table
- **Enable/disable comments** — post owners can toggle whether comments are allowed
- **Hashtag support** — posts can include hashtags, searchable via the search endpoint
- **Post sharing** — any post can be shared into a DM conversation
- **Owner info** — every post response includes the author's basic profile info

---

## 💬 Comments

- **Full CRUD** — create, edit, and delete comments on any post (if comments are enabled)
- **Paginated retrieval** — fetch comments on any post with configurable `limit` and `offset`
- **Like comments** — toggle-based like system for individual comments via a dedicated `CommentVotes` table with database-synced comment counters
- **Comment stats** — view your total comment count and the number of unique posts you've commented on
- **Owner-only edit/delete** — only the comment author can modify or remove their comment
- **Cascading deletes** — when a post is deleted, all its comments are automatically cleaned up

---

## 👍 Voting / Likes System

- **Toggle-based voting on posts** — like (`true`) or dislike (`false`) any post
  - Voting the same way again **removes** the vote
  - Voting the opposite way **switches** the vote (e.g., like → dislike)
- **Toggle-based liking on comments** — like a comment; like again to remove
- **Separate tracking tables** — `Votes` for posts, `CommentVotes` for comments, with unique constraints to prevent duplicate entries
- **Analytics & stats:**
  - View all posts you've voted on
  - See your like vs. dislike counts
  - List all your liked posts
  - List all your disliked posts
- **Database-synced count updates** — like/dislike counts on posts and comments are kept in sync by the database while the vote rows remain the source of truth

---

## 📰 Feed System

- **Home feed** — shows posts from users you follow, sorted most-recent-first, with pagination
- **Explore feed** — shows all posts on the platform, ordered by newest, with pagination
- **`is_liked` flag** — every post in the feed indicates whether the current user has liked it
- **Owner info** — each feed item includes the post author's username and profile picture
- **Configurable pagination** — `limit` (1–100) and `offset` query parameters on both feeds

---

## 🔖 Saved Posts

- **Personal save collection** — each user can save posts they want to revisit later
- **Three dedicated endpoints:**
  - `POST /v1/posts/{post_id}/save` — save a post
  - `DELETE /v1/posts/{post_id}/unsave` — remove from saved
  - `GET /v1/users/me/saved-posts` — list saved posts newest-first
- **Duplicate-safe behavior** — saving the same post twice does not create duplicates (unique `(user_id, post_id)` constraint)
- **Rich response model** — each saved item returns `saved_at` plus a full `PostDetailResponse` payload
- **Per-user like context** — saved list includes `is_liked` for each post from the perspective of the current user
- **Automatic cleanup** — saved rows are removed automatically if a user or post is deleted (foreign keys with cascade)

---

## 🔍 Search

- **User search** — search by username with partial matching (`ILIKE`) backed by a PostgreSQL trigram index.

(**Removed the pg_trgm PostgreSQL extension, as it is not allowed in the Azure Database for PostgreSQL**)

- **Hashtag search** — prefix query with `#` to search posts by hashtag, ranked with trigram similarity
- **Order by likes** — hashtag search results can be sorted by like count (`orderBy=likes`)
- **Paginated results** — both user and post search support `limit` and `offset`
- **Response type indicator** — the response includes `result_type` ("users" or "posts") so the client knows what it received

---

## 🔒 Password Management

- **Change password (authenticated):**
  1. Request an OTP → sent to your registered email
  2. Submit old password + new password + OTP → password updated
- **Forgot password (unauthenticated):**
  1. Submit your email → OTP sent (no user enumeration — generic response)
  2. Submit email + OTP + new password → password reset
- **OTP system:**
  - 6-digit random OTP stored in the database as a SHA-256 digest with expiration time
  - Only one active OTP per email (old ones are deleted)
  - Auto-cleanup of expired OTPs
- **Email delivery** — OTPs sent via Gmail SMTP using `fastapi-mail` (async, non-blocking)

---

## 💬 Real-Time Chat (WebSockets)

A production-grade 1-on-1 chat system running over a single persistent WebSocket connection per user.

### Connection & Authentication
- **JWT-authenticated WebSocket** — token passed as a query parameter; spoofing protection (user ID in URL must match token)
- **Auto-delivery of missed content** — on connect, all unread messages and shared posts are automatically pushed to the client
- **Graceful disconnect handling** — distinguishes between client-initiated and server-initiated disconnects

### Messaging
- **Direct messages** — send text messages to any user by their ID
- **Media messages** — send images, videos, and audio files (upload first via REST, then pass the URL in the WebSocket message)
- **Reply to messages** — reply to any message with a reference to the original (content + sender preserved)
- **Reply to shared posts** — reply directly to a post that was shared into the conversation

### Live Features
- **Typing indicators** — real-time "user is typing..." status pushed to the other party
- **Online/offline detection** — users are marked online when their WebSocket connects, and marked offline if they disconnect or stop sending presence heartbeats
- **Presence heartbeats** — clients send `presence_heartbeat` at intervals; server replies with `presence_ack` and uses timeout to detect zombie sessions
- **Instant presence updates** — a dedicated `presence_update` event is broadcast to conversation peers on connect/disconnect
- **Last seen tracking** — `last_seen_at` is persisted on disconnect and included in presence payloads
- **Read receipts** — mark all unread messages from a sender as read; the sender gets a real-time notification with the read timestamp
- **Message reactions (emoji)** — react to any message with any emoji; toggle behavior (same emoji = remove, different emoji = switch)

### Delivery Guarantees
- **Instant delivery if online** — message is pushed via WebSocket and immediately marked as read
- **Offline queue** — if the receiver is offline, the message is stored in the database and delivered on their next connection
- **Sender confirmation** — every sent message is echoed back to the sender with the server-assigned ID and timestamp

---

## ✏️ Message Controls

- **Edit messages** — update message content within a configurable time window (default: 15 minutes)
  - `can_edit` REST endpoint to check eligibility before showing the UI option
  - Edited messages are flagged with `is_edited: true` and timestamped with `edited_at`
  - Both sender and receiver receive the edit via WebSocket in real time
  - Re-marks the message as unread for the receiver after an edit
- **Delete for me** — hides a message from your view only (stored in a `DeletedMessage` table with unique constraint to prevent duplicates)
- **Delete for everyone** ("unsend") — marks the message as `is_deleted_for_everyone`; both parties receive instant WebSocket notification
- **Clear chat** — bulk-deletes all visible messages in a conversation from your view using an efficient batched `INSERT ... FROM SELECT` operation
- **Rate-limited editing** — time window is server-configurable via the `MAX_EDIT_TIME` environment variable

---

## 📤 Post Sharing into DMs

- **Share any post** into a 1-on-1 DM conversation with an optional caption message
- **Real-time delivery** — if the receiver is online, they get an instant WebSocket preview with post title, media, and sender info
- **React to shared posts** — emoji reactions on shared posts with the same toggle behavior as message reactions
- **Reply to shared posts** — reply directly to a shared post with text or media
- **Delete shared posts** — both "delete for me" and "delete for everyone" supported
- **Shared post tracking** — dedicated `SharedPost`, `SharedPostReaction`, `SharedPostReplies`, and `DeletedSharedPost` tables

---

## 🚀 Redis Caching & Token Blacklisting

- **Response caching across 11+ endpoints** — frequently accessed data is cached in Redis with endpoint-specific TTLs:
  | Cached Endpoint | Cache Key Pattern | TTL |
  |----------------|-------------------|-----|
  | User profile | `user_profile:{id}` | 120s |
  | All users list | `all_users` | 120s |
  | Home feed | `feed:home:{user}:{offset}:{limit}` | 30s |
  | Explore feed | `feed:explore:{user}:{offset}:{limit}` | 60s |
  | Post detail | `post:{id}:{user}` | 120s |
  | Comments on post | `comments:post:{id}:{offset}:{limit}` | 30s |
  | User's followers | `followers:{user_id}` | 120s |
  | User's following | `following:{user_id}` | 120s |
  | User's posts | `user:posts:{id}:{offset}:{limit}` | 60s |
  | Notifications | `notifications:{user}:{offset}:{limit}` | 20s |
  | Unread count | `notif:unread:{user}` | 20s |
- **Automatic cache invalidation on writes** — every mutating operation clears related caches:
  - Post create/edit/delete → clears `post:*`, `feed:*`, `user:posts:*`
  - Comment create/edit/delete → clears `comments:post:*`, `post:*`
  - Vote add/remove/switch → clears `post:*`, `feed:*`
  - Follow/unfollow/remove → clears `followers:*`, `following:*`, `feed:home:*`, `user_profile:*`
  - Notification created → clears `notifications:*`, `notif:unread:*`
- **Pattern-based invalidation** — `delete_cache_pattern("feed:*")` uses `SCAN` (non-blocking, unlike `KEYS`) to find and delete matching keys
- **Token blacklisting** — on logout, the JWT is stored in Redis with its remaining TTL; every authenticated request checks the blacklist before processing
- **Graceful degradation** — if Redis is unavailable, the API still works (cache misses fall through to the database); cache failures never cause 500 errors
- **Startup health check** — Redis connectivity is verified on application startup with a clear success/failure message

---

## 📁 Media & File Management

- **Dual storage mode (Azure + local fallback):**
  - Production/hosted deployment uses Azure Blob Storage when blob env vars are configured.
  - Local clones run without Azure keys by automatically storing media in local folders.
- **Three separate media directories:**
  - `profilepics/` — user profile pictures
  - `posts_media/` — post images and videos
  - `chat-media/` — chat images, videos, and audio files (organized into `images/`, `videos/`, `audios/` subdirectories)
- **Local fallback storage** — when Azure Blob env values are empty, uploads are persisted to local folders and served through mounted static routes
- **Static file serving** — all three directories are mounted as FastAPI `StaticFiles` endpoints, so media URLs are directly accessible in the browser
- **Supported formats:**
  - Profile pictures: JPEG, PNG, GIF
  - Post media: JPEG, PNG, MP4
  - Chat media: any image, video, or audio file
- **UUID-based naming** — uploaded files are renamed with UUIDs to prevent filename collisions
- **Cleanup on delete** — media files are removed from disk when their associated post or profile picture is deleted

---

## 🗄️ Database & Migrations

- **PostgreSQL 16** — production-grade relational database
- **SQLAlchemy 2.0** — modern ORM with both async (`AsyncSession`) and sync engines
- **Async database driver** — `asyncpg` for fully non-blocking database I/O
- **Alembic migrations** — auto-run on container startup (`alembic upgrade head`); version-controlled schema changes, counter triggers, check constraints, and search indexes
- **Declarative models** — 16+ database tables:
  - `users`, `posts`, `post_views`, `comments`, `votes`, `comment_votes`
  - `connections` (follow system)
  - `notifications` (like, comment, follow events)
  - `refresh_tokens` (opaque tokens with family-based rotation)
  - `messages`, `message_replies`, `message_reactions`, `deleted_messages`
  - `shared_posts`, `shared_post_replies`, `shared_post_reactions`, `deleted_shared_posts`
  - `otps` (OTP storage)
- **Eager loading** — `lazy="selectin"` on all relationships to avoid N+1 query problems
- **Cascading deletes** — `ondelete="CASCADE"` on all foreign keys for automatic cleanup
- **Unique constraints** — prevents duplicate votes, reactions, deleted message records, etc.
- **Derived-state sync** — triggers keep post/comment/reaction/follow counters aligned with the source tables
- **Search support** — PostgreSQL `pg_trgm` indexes speed up username and hashtag search
- **Secret hardening** — refresh tokens and OTPs are hashed before storage

---

## 🐳 DevOps & Docker

- **Docker Compose** multi-service stack:
  - `api` — FastAPI application (Python 3.12, auto-reload in dev)
  - `db` — PostgreSQL 16 Alpine
  - `redis` — Redis 7 Alpine
- **Bind-mount volumes** — code changes reflect instantly without rebuilding
- **Named persistent volumes** — PostgreSQL data survives container restarts
- **Auto-restart** — `restart: unless-stopped` on API and Redis services
- **Automatic migrations** — Alembic runs `upgrade head` before the server starts on every container launch
- **Inter-service networking** — API connects to `db` and `redis` via Docker service names
- **Port mapping** — API on `8000`, PostgreSQL on `5432`, Redis on `6379`

---

## 📚 API Documentation

- **Swagger UI** — auto-generated interactive docs at `/docs` — test every endpoint directly in the browser
- **ReDoc** — alternative clean API reference at `/redoc`
- **Pydantic schemas** — strongly typed request/response models with validation:
  - Field constraints (`min_length`, `max_length`, `ge`, `le`)
  - Email validation via `EmailStr`
  - Optional fields with proper defaults
  - `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
- **Health check endpoint** — `GET /health` for monitoring and uptime checks
- **Detailed API guide** — handwritten [`API_GUIDE.md`](./API_GUIDE.md) covering all 55+ REST endpoints and WebSocket message types with examples

---

## 🚦 API Versioning

The API follows a strict versioning policy to ensure stability and backward compatibility for all clients.

- **Global Prefix** — All endpoints are prefixed with their version (e.g., `/v1/auth/login`, `/v1/posts`).
- **Breaking Change Policy** — We never modify existing versioned endpoints in a way that breaks current clients. Instead, we introduce a new version (e.g., `/v2/`) for significant architectural or schema changes.
- **Router-Level Isolation** — Each version is managed via separate FastAPI routers, allowing us to maintain multiple versions concurrently without code bloat.
- **Consistent Documentation** — Both Swagger and the handwritten guides are updated to reflect the current active versions and their specific request/response models.

---

## 🧪 Testing

- **Pytest** test suite with **50+ integration tests** covering:
  - Authentication & authorization
  - User management & profiles
  - Posts CRUD operations
  - Comments & interactions
  - Follow/unfollow system
  - Real-time chat (WebSockets)
  - Search & feed features
  - Schema validation
  - Edge cases & integration tests
- **Isolated test database** — uses a separate `fastapi_test` database so dev data is never affected
- **Docker-aware** — auto-detects `/.dockerenv` and switches the database host to `db`
- **Detailed test guide** — [`TESTS.md`](./TESTS.md) with commands, tips, and debugging advice

---

## 📈 Observability and Load Testing

- **OpenTelemetry tracing** — FastAPI and SQLAlchemy request spans are instrumented to expose request flow and DB timing.
- **Prometheus metrics** — `/metrics` endpoint is exposed for scrape-based monitoring.
- **Grafana dashboards** — project includes provisioned dashboard and datasource setup for quick startup.
- **k6 load scripts** — smoke, load, and stress scenarios are included under `loadtests/` for repeatable performance validation.
- **Route-aware checks** — k6 scripts validate endpoint reachability with expected status handling for protected and heavy routes.
- **Performance bottleneck discovery** — setup is designed to reveal latency tail growth, timeout behavior, and transport-level failures (EOF/connect timeout) under pressure.

---

> Built with ❤️ using FastAPI, SQLAlchemy, PostgreSQL, Redis, WebSockets & Real-Time Pub/Sub
