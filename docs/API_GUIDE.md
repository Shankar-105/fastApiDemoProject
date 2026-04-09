# 📖 API Guide — Complete Endpoint Reference

> **Your one-stop reference for every REST and WebSocket endpoint in the SocialMediaApi.**

### 📊 At a Glance

| Type | Count |
|------|-------|
| **REST Endpoints** | **55** |
| **WebSocket Endpoints** | **1** (`/chat/ws/{user_id}`) |
| **WebSocket Message Types** | **11** (send) + **7** (receive) |

---

## ⚠️ Before You Begin

Before calling **any** endpoint, make sure you have:

1. ✅ Completed the full **[SETUP.md](./SETUP.md)** — cloned the repo, configured `.env`, and prepared local folders.
2. ✅ Docker containers are **running** — `docker compose up -d` and verified via `http://localhost:8000/health`.
3. ✅ A tool to make HTTP requests — **[Postman](https://www.postman.com/)**, **[Insomnia](https://insomnia.rest/)**, **cURL**, **HTTPie**, or the built-in **Swagger UI** at `http://localhost:8000/docs`.

> 💡 **Tip:** FastAPI auto-generates interactive API docs. Visit **`http://localhost:8000/docs`** (Swagger UI) or **`http://localhost:8000/redoc`** (ReDoc) to explore and test endpoints right from your browser.

---

## 🔑 Authentication — How It Works

Most endpoints require a **JWT Bearer Token**. Here's the flow:

1. **Sign up** → `POST /user/signup`
2. **Log in** → `POST /login` → you receive an `accessToken` + `refreshToken`
3. **Use the access token** in subsequent requests:
   - **Header:** `Authorization: Bearer <your_access_token>`
   - **Postman:** Go to the *Authorization* tab → select *Bearer Token* → paste your token.
   - **cURL:** `curl -H "Authorization: Bearer <token>" http://localhost:8000/me/profile`
4. **When the access token expires** → call `POST /refresh` with your `refreshToken` to get a fresh pair (old refresh token is revoked)
5. **Log out** → `POST /logout` — blacklists the access token and revokes all refresh tokens for that user

> 🔒 Endpoints marked with 🔐 require authentication. Public endpoints are marked with 🌐.
> 
> 🛡️ Several sensitive endpoints are **rate-limited** (marked with ⚡). Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

---

## 📑 Table of Contents

| Section | Description |
|---------|-------------|
| [Health Check](#-health-check) | Verify the API is running |
| [Authentication](#-authentication) | Sign up, log in, refresh tokens, logout |
| [My Profile (me)](#-my-profile-me) | View/update your own profile, posts, stats |
| [Notifications](#-notifications) | View, count, and mark notifications as read |
| [Users](#-users) | View other users, their posts, followers |
| [Posts](#-posts) | Create, read, update, delete posts |
| [Comments](#-comments) | Comment on posts (CRUD) |
| [Votes / Likes](#-votes--likes) | Like/dislike posts and comments |
| [Connections](#-connections-followunfollow) | Follow, unfollow, remove followers |
| [Feed](#-feed) | Home feed & explore |
| [Search](#-search) | Search users & hashtags |
| [Password Management](#-password-management) | Change/reset password via OTP (authenticated & unauthenticated) |
| [Chat — Recent Chats](#-chat--recent-chats) | List recent conversations |
| [Chat — Share Posts](#-chat--share-posts) | Share posts into DMs |
| [Chat — Media Upload](#-chat--media-upload) | Upload images/videos/audio for chat |
| [Chat — Message Info & Reactions](#-chat--message-info--reactions) | Message details, reactions |
| [Chat — Delete & Clear](#-chat--delete--clear) | Delete messages, shares, clear chat |
| [Chat — Edit Messages](#-chat--edit-messages) | Check edit eligibility |
| [WebSocket — Real-Time Chat](#-websocket--real-time-chat) | Live messaging, typing, reactions |

---

## 💚 Health Check

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /health` |
| **Auth** | 🌐 None |
| **Description** | Quick check to see if the API server is alive. |

**Example — cURL:**
```bash
curl http://localhost:8000/health
```

**Response — `200 OK`:**
```json
{
  "message": "fine"
}
```

---
## 🔐 Authentication

### 1. Sign Up

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /user/signup` |
| **Auth** | 🌐 None |
| **Content-Type** | `application/json` |
| **Description** | Register a new user account. |

**Request Body:**
```json
{
  "username": "john_doe",
  "password": "securePass123",
  "nickname": "Johnny",
  "email": "john@example.com"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | ✅ | 3–50 chars, must be unique |
| `password` | string | ✅ | 6–72 chars, stored hashed (bcrypt) |
| `nickname` | string | ❌ | Max 50 chars |
| `email` | string | ❌ | Valid email format |

**Response — `201 Created`:**
```json
{
  "id": 1,
  "username": "john_doe",
  "created_at": "2026-02-09T10:30:00.000Z"
}
```

---

### 2. Log In

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /login` |
| **Auth** | 🌐 None |
| **Rate Limit** | ⚡ 5 requests / 5 min per IP |
| **Content-Type** | `application/x-www-form-urlencoded` |
| **Description** | Authenticate and receive a JWT access token + refresh token. |

**Request Body (form data):**
| Field | Type | Required |
|-------|------|----------|
| `username` | string | ✅ |
| `password` | string | ✅ |

**cURL Example:**
```bash
curl -X POST http://localhost:8000/login \
  -d "username=john_doe&password=securePass123"
```

**Response — `202 Accepted`:**
```json
{
  "id": 1,
  "username": "john_doe",
  "accessToken": "eyJhbGciOiJIUzI1NiIs...",
  "refreshToken": "a1b2c3d4e5f6...",
  "tokenType": "bearer"
}
```

> 📌 **Save both tokens!** Use `accessToken` as a Bearer token for all authenticated endpoints. Use `refreshToken` to silently get a new access token when the current one expires.

---

### 3. Refresh Token

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /refresh` |
| **Auth** | 🌐 None |
| **Rate Limit** | ⚡ 10 requests / 1 min per IP |
| **Content-Type** | `application/json` |
| **Description** | Exchange a valid refresh token for a new access + refresh token pair. The old refresh token is revoked (rotation). |

**Request Body:**
```json
{
  "refresh_token": "a1b2c3d4e5f6..."
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "a1b2c3d4e5f6..."}'
```

**Response — `200 OK`:**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIs...",
  "refreshToken": "x7y8z9w0..."
}
```

> ⚠️ **Security:** If a revoked refresh token is reused (replay attack), the entire token family is invalidated, forcing re-login on all devices.

---

### 4. Logout

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /logout` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Blacklists the current access token and revokes all refresh tokens for the user. |

**cURL Example:**
```bash
curl -X POST http://localhost:8000/logout \
  -H "Authorization: Bearer <token>"
```

**Response — `200 OK`:**
```json
{
  "message": "Successfully logged out"
}
```

> After logout, both the access token and all refresh tokens are invalidated. The user must log in again to get new tokens.

---

## 👤 My Profile (me)

All `/me/*` endpoints operate on the **currently authenticated user**.

### 1. Get My Profile

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/profile` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve your complete profile information. |

**Response — `200 OK`:**
```json
{
  "id": 1,
  "username": "john_doe",
  "nickname": "Johnny",
  "bio": "Hello world!",
  "profile_picture": "john_doe_avatar.png",
  "posts_count": 5,
  "followers_count": 12,
  "following_count": 8,
  "created_at": "2026-02-09T10:30:00.000Z"
}
```

---

### 2. Get My Profile Picture

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/profile/pic` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get the URL of your current profile picture. |

**Response — `200 OK`:**
```json
{
  "url": "http://localhost:8000/profilepics/john_doe_avatar.png",
  "type": "image"
}
```

> Returns `404` if no profile picture is set.

---
### 3. Delete My Profile Picture

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /me/profilepic/delete` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Remove your current profile picture. |

**Response — `200 OK`:**
```json
{
  "message": "Profile picture removed successfully"
}
```

---

### 4. Update My Info

| Detail | Value |
|--------|-------|
| **Endpoint** | `PATCH /me/updateInfo` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `multipart/form-data` |
| **Description** | Update username, bio, and/or profile picture. All fields are optional. |

**Form Fields:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `username` | string | ❌ | New username (must be unique) |
| `bio` | string | ❌ | Your bio text |
| `profile_picture` | file | ❌ | JPEG, PNG, or GIF only |

**cURL Example:**
```bash
curl -X PATCH http://localhost:8000/me/updateInfo \
  -H "Authorization: Bearer <token>" \
  -F "bio=I love coding!" \
  -F "profile_picture=@/path/to/avatar.png"
```

**Response — `200 OK`:** Returns the full updated `UserProfileResponse`.

---

### 5. Get My Posts

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/posts` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve all your posts with pagination. |

**Query Parameters:**
| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int | `10` | 1–100 |
| `offset` | int | `0` | Skip N posts |

**Response — `200 OK`:**
```json
{
  "posts": [
    {
      "id": 1,
      "title": "My first post!",
      "media_url": "http://localhost:8000/posts_media/abc.jpg",
      "media_type": "image",
      "likes": 5,
      "comments_count": 2,
      "created_at": "2026-02-09T12:00:00.000Z",
      "is_liked": true
    }
  ],
  "pagination": {
    "total": 1,
    "limit": 10,
    "offset": 0,
    "has_more": false
  }
}
```

---
### 6. Get Posts I Voted On

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/votedOnPosts` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Lists all posts you have voted (liked or disliked) on. |

**Response — `200 OK`:**
```json
{
  "john_doe you have voted on posts": [
    {
      "post title": "Amazing sunset",
      "post id": "3",
      "post owner": "jane_doe"
    }
  ]
}
```

---

### 7. Get My Vote Stats

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/voteStats` |
| **Auth** | 🔐 Bearer Token |
| **Description** | See how many posts you've liked vs disliked. |

**Response — `200 OK`:**
```json
{
  "liked_posts_count": 15,
  "disliked_posts_count": 3
}
```

---

### 8. Get My Liked Posts

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/likedPosts` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Lists all posts you have liked. |

**Response — `200 OK`:**
```json
{
  "john_doe your liked posts includes": [
    { "post id": 3, "post owner": "jane_doe" },
    { "post id": 7, "post owner": "alice" }
  ]
}
```

---

### 9. Get My Disliked Posts

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/dislikedPosts` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Lists all posts you have disliked. |

**Response — `200 OK`:**
```json
{
  "john_doe your disliked posts includes": [
    { "post id": 5, "post owner": "bob" }
  ]
}
```

---

### 10. Get Posts I Commented On

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/commented-on` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Lists all unique posts you've commented on. |

**Response — `200 OK`:**
```json
{
  "john_doe you have commented on posts": [
    {
      "post title": "Check this out",
      "post id": "4",
      "post owner": "alice"
    }
  ]
}
```

---

### 11. Get My Comment Stats

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/comment-stats` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get the total number of comments you've made and unique posts commented on. |

**Response — `200 OK`:**
```json
{
  "total_comments": 42,
  "unique_posts_commented": 18
}
```

---

## � Notifications

### 1. Get My Notifications

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/notifications` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve your notifications (likes, comments, follows), newest first. Cached for 20s. |

**Query Parameters:**
| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int | `20` | 1–100 |
| `offset` | int | `0` | Skip N notifications |

**Response — `200 OK`:**
```json
{
  "notifications": [
    {
      "id": 1,
      "type": "like",
      "text": "jane_doe liked your post",
      "actor_username": "jane_doe",
      "is_read": false,
      "created_at": "2026-03-06T10:30:00Z",
      "entity_type": "post",
      "entity_id": 5
    }
  ],
  "unread_count": 3,
  "total": 10,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

---

### 2. Get Unread Notification Count

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /me/notifications/unread-count` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Returns the number of unread notifications — use this for the badge number in your UI. Cached for 20s. |

**Response — `200 OK`:**
```json
{
  "count": 3
}
```

---

### 3. Mark All Notifications as Read

| Detail | Value |
|--------|-------|
| **Endpoint** | `PATCH /me/notifications/read` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Marks all unread notifications as read for the current user. |

**Response — `200 OK`:**
```json
{
  "message": "All notifications marked as read"
}
```

---

## �👥 Users

### 1. Get All Users

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/getAllUsers` |
| **Auth** | 🌐 None |
| **Description** | Retrieve a list of all registered users. |

**Response — `201 Created`:**
```json
[
  {
    "id": 1,
    "username": "john_doe",
    "created_at": "2026-02-09T10:30:00.000Z"
  },
  {
    "id": 2,
    "username": "jane_doe",
    "created_at": "2026-02-09T11:00:00.000Z"
  }
]
```

---

### 2. Get User Profile

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/{user_id}/profile` |
| **Auth** | 🔐 Bearer Token |
| **Description** | View another user's profile. Includes `is_following` status. |

**Response — `200 OK`:**
```json
{
  "id": 2,
  "username": "jane_doe",
  "nickname": "Jane",
  "bio": "Photographer 📸",
  "profile_picture": "jane_avatar.png",
  "posts_count": 10,
  "followers_count": 50,
  "following_count": 30,
  "is_following": true,
  "created_at": "2026-02-09T11:00:00.000Z"
}
```

---

### 3. Get User Profile Picture

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/{user_id}/profile/pic` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get the profile picture URL of a specific user. |

**Response — `200 OK`:**
```json
{
  "url": "http://localhost:8000/profilepics/jane_avatar.png",
  "type": "image"
}
```

---

### 4. Get User's Posts

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/{user_id}/posts` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve a specific user's posts with pagination. |

**Query Parameters:**
| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | int | `10` | 1–100 |
| `offset` | int | `0` | Skip N posts |

**Response — `200 OK`:** Same structure as `GET /me/posts`.

---

### 5. Get User's Followers

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/{user_id}/followers` |
| **Auth** | 🔐 Bearer Token |
| **Description** | List all followers of a specific user. |

**Response — `200 OK`:**
```json
[
  {
    "id": 1,
    "username": "john_doe",
    "nickname": "Johnny",
    "profile_pic": "john_avatar.png",
    "is_following": false
  }
]
```

---

### 6. Get User's Following

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /users/{user_id}/following` |
| **Auth** | 🔐 Bearer Token |
| **Description** | List all users a specific user is following. |

**Response — `200 OK`:** Same structure as followers list.

---

## 📝 Posts

### 1. Create Post

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /posts/createPost` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `multipart/form-data` |
| **Description** | Create a new post with text and optional media (image/video). |

**Form Fields:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | ✅ | Post title |
| `content` | string | ✅ | Post body text |
| `media` | file | ❌ | JPEG, PNG, or MP4 only |

**cURL Example:**
```bash
curl -X POST http://localhost:8000/posts/createPost \
  -H "Authorization: Bearer <token>" \
  -F "title=My first post" \
  -F "content=Hello world!" \
  -F "media=@/path/to/photo.jpg"
```

**Response — `201 Created`:**
```json
{
  "id": 1,
  "title": "My first post",
  "content": "Hello world!",
  "media_url": "http://localhost:8000/posts_media/abc123.jpg",
  "media_type": "image",
  "likes": 0,
  "dislikes": 0,
  "views": 0,
  "comments_count": 0,
  "enable_comments": true,
  "hashtags": null,
  "created_at": "2026-02-09T12:00:00.000Z",
  "owner": {
    "id": 1,
    "username": "john_doe",
    "nickname": "Johnny",
    "profile_pic": null
  }
}
```

---

### 2. Get Post by ID

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /posts/getPost/{postId}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get full details of a specific post. Increments the view counter on first view. |

**Response — `200 OK`:** Full `PostDetailResponse` (same structure as create post response, plus `is_liked` field).

---

### 3. Edit Post

| Detail | Value |
|--------|-------|
| **Endpoint** | `PUT /posts/editPost/{postId}` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Update the title, content, or other fields of your post. Only the post owner can edit. |

**Request Body (all fields optional):**
```json
{
  "title": "Updated title",
  "content": "Updated content"
}
```

**Response — `200 OK`:** Full `PostDetailResponse` with updated data.

---

### 4. Delete Post

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /posts/deletePost/{postId}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Permanently delete your post and its associated media file. |

**Response — `200 OK`:**
```json
{
  "message": "Post 1 deleted successfully"
}
```

---
## 💬 Comments

### 1. Create Comment

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /comment` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Add a comment to a post (if comments are enabled on that post). |

**Request Body:**
```json
{
  "post_id": 1,
  "content": "Great post!"
}
```

**Response — `201 Created`:**
```json
{
  "id": 1,
  "post_id": 1,
  "content": "Great post!",
  "likes": 0,
  "created_at": "2026-02-09T13:00:00.000Z",
  "user": {
    "id": 1,
    "username": "john_doe",
    "nickname": "Johnny",
    "profile_pic": null
  }
}
```

---

### 2. Get Comments on a Post

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /comments-on/{post_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve paginated comments on a specific post. |

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `limit` | int | `10` |
| `offset` | int | `0` |

**Response — `200 OK`:**
```json
{
  "comments": [
    {
      "id": 1,
      "post_id": 1,
      "content": "Great post!",
      "likes": 3,
      "created_at": "2026-02-09T13:00:00.000Z",
      "user": {
        "id": 2,
        "username": "jane_doe",
        "nickname": "Jane",
        "profile_pic": null
      }
    }
  ],
  "pagination": {
    "total": 1,
    "limit": 10,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 3. Edit Comment

| Detail | Value |
|--------|-------|
| **Endpoint** | `PATCH /comments/edit_comment/{comment_id}` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Edit the content of your comment. |

**Request Body:**
```json
{
  "comment_content": "Updated comment text"
}
```

**Response — `200 OK`:** Full `CommentDetailResponse`.

---

### 4. Delete Comment

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /comments/delete_comment/{comment_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Delete your comment. |

**Response — `200 OK`:**
```json
{
  "message": "Comment 1 deleted successfully"
}
```

---

## 👍 Votes / Likes

### 1. Vote on a Post

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /vote/on_post` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Like or dislike a post. Acts as a toggle — same vote again removes it, different vote switches it. |

**Request Body:**
```json
{
  "post_id": 1,
  "choice": true
}
```

| Field | Type | Notes |
|-------|------|-------|
| `post_id` | int | The post to vote on |
| `choice` | bool | `true` = like, `false` = dislike |

**Response — `201 Created`:**
```json
{
  "message": "New vote added successfully",
  "likes": 6,
  "dislikes": 1
}
```

> **Toggle behavior:**
> - Vote the same way again → vote removed (`"Vote removed successfully"`)
> - Vote the opposite way → vote switched (`"Vote switched successfully"`)

---

### 2. Vote on a Comment

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /vote/on_comment` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Like a comment. Toggle same choice to remove the like. |

**Request Body:**
```json
{
  "comment_id": 1,
  "choice": true
}
```

**Response — `201 Created`:**
```json
{
  "message": "New vote added successfully",
  "likes": 4
}
```

---

## 🔗 Connections (Follow/Unfollow)

### 1. Follow a User

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /follow/{user_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Follow a user. Cannot follow yourself. |

**Response — `201 Created`:**
```json
{
  "message": "Followed user jane_doe",
  "following_count": 9
}
```

---

### 2. Unfollow a User

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /unfollow/{user_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Unfollow a user you're currently following. |

**Response — `200 OK`:**
```json
{
  "message": "Unfollowed user jane_doe",
  "following_count": 8
}
```

---

### 3. Remove a Follower

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /remove_follower/{user_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Remove someone from your followers list (they stop following you). |

**Response — `200 OK`:**
```json
{
  "message": "Removed follower bob",
  "following_count": 8
}
```

---

## 📰 Feed

### 1. Home Feed

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /feed/home` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get posts from users you follow, most recent first. |

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `limit` | int | `10` |
| `offset` | int | `0` |

**Response — `200 OK`:**
```json
{
  "feed": [
    {
      "post_id": 5,
      "post": {
        "id": 5,
        "title": "Sunset vibes 🌅",
        "media_url": "http://localhost:8000/posts_media/sunset.jpg",
        "media_type": "image",
        "likes": 12,
        "comments_count": 3,
        "created_at": "2026-02-09T18:00:00.000Z",
        "is_liked": true
      },
      "owner": {
        "id": 2,
        "username": "jane_doe",
        "profile_pic": "jane_avatar.png"
      }
    }
  ],
  "total": 1
}
```

---

### 2. Explore Feed

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /feed/explore` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Discover all posts on the platform, most recent first. |

**Query Parameters:**
| Param | Type | Default |
|-------|------|---------|
| `limit` | int | `20` |
| `offset` | int | `0` |

**Response — `200 OK`:** Same paginated `PostListResponse` structure as `GET /me/posts`.

---

## 🔍 Search

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /search` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Search for users by username **or** posts by hashtag (`#tag`). |

**Query Parameters:**
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `q` | string | ✅ | Search query. Prefix with `#` for hashtag search. |
| `limit` | int | ❌ | Default `10` |
| `offset` | int | ❌ | Default `0` |
| `orderBy` | string | ❌ | Use `"likes"` to sort hashtag results by likes |

**Example — Search users:**
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/search?q=john"
```

**Response (user search) — `202 Accepted`:**
```json
{
  "result_type": "users",
  "users": [
    {
      "id": 1,
      "username": "john_doe",
      "nickname": "Johnny",
      "profile_pic": null
    }
  ],
  "total": 1
}
```

**Example — Search hashtags:**
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/search?q=%23sunset"
```

**Response (hashtag search) — `202 Accepted`:**
```json
{
  "result_type": "posts",
  "posts": [
    {
      "id": 5,
      "title": "Sunset vibes 🌅",
      "media_url": "http://localhost:8000/posts_media/sunset.jpg",
      "media_type": "image",
      "likes": 12,
      "comments_count": 3,
      "created_at": "2026-02-09T18:00:00.000Z"
    }
  ],
  "total": 1
}
```

---

## 🔒 Password Management

### 1. Request OTP (Initiate Password Change — Authenticated)

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /change-password` |
| **Auth** | 🔐 Bearer Token |
| **Rate Limit** | ⚡ 3 requests / 1 hour per user |
| **Description** | Sends a one-time password (OTP) to your registered email. Required before resetting your password. |

**Response — `200 OK`:**
```json
{
  "message": "OTP sent to your email! Check inbox"
}
```

> ⚠️ Requires a valid Gmail + App Password configured in `.env` (see SETUP.md).

---

### 2. Reset Password (Authenticated, with OTP)

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /reset-password` |
| **Auth** | 🔐 Bearer Token |
| **Rate Limit** | ⚡ 5 requests / 5 min per user |
| **Content-Type** | `application/json` |
| **Description** | Change your password after verifying the OTP sent to your email. Revokes all refresh tokens after password change. |

**Request Body:**
```json
{
  "old_password": "currentPass123",
  "new_password": "brandNewPass456",
  "otp": "123456"
}
```

**Response — `200 OK`:**
```json
{
  "message": "Password changed successfully! Now login with new one."
}
```

---

### 3. Forgot Password (Unauthenticated)

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /forgot-password` |
| **Auth** | 🌐 None |
| **Rate Limit** | ⚡ 3 requests / 1 hour per IP |
| **Content-Type** | `application/json` |
| **Description** | Initiate a password reset without being logged in. Sends an OTP to the provided email. Response is always the same to prevent user enumeration. |

**Request Body:**
```json
{
  "email": "john@example.com"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "john@example.com"}'
```

**Response — `200 OK`:**
```json
{
  "message": "If an account with this email exists, an OTP has been sent."
}
```

---

### 4. Reset Password (Unauthenticated, with OTP)

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /reset-password` (auth.py) |
| **Auth** | 🌐 None |
| **Rate Limit** | ⚡ 5 requests / 5 min per IP |
| **Content-Type** | `application/json` |
| **Description** | Complete the forgot-password flow by submitting the email, OTP, and new password. |

**Request Body:**
```json
{
  "email": "john@example.com",
  "otp": "123456",
  "new_password": "brandNewPass456"
}
```

**Response — `200 OK`:**
```json
{
  "message": "Password has been reset successfully. Please login with your new password."
}
```

---

## 💬 Chat — Recent Chats

### 1. Get Recent Conversations

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /recent-chats` |
| **Auth** | 🔐 Bearer Token |
| **Description** | List your recent chat conversations with a summary of the last message in each. |

**Response — `200 OK`:**
```json
[
  {
    "id": 2,
    "username": "jane_doe",
    "nickname": "Jane",
    "profile_pic": "jane_avatar.png",
    "last_message": {
      "content": "See you tomorrow!",
      "timestamp": "2 hours ago"
    }
  }
]
```

---
## 📤 Chat — Share Posts

### 1. Share a Post into DMs

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /share` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `application/json` |
| **Description** | Share a post to another user via direct message. The receiver gets a real-time notification if online. |

**Request Body:**
```json
{
  "post_id": 5,
  "to_user_id": 2,
  "message": "Check out this post!"
}
```

**Response — `200 OK`:** Returns the full `SharedPostDetailResponse` with the shared post details.

---

## 📎 Chat — Media Upload

### 1. Upload Chat Media

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /upload-media` |
| **Auth** | 🔐 Bearer Token |
| **Content-Type** | `multipart/form-data` |
| **Description** | Upload an image, video, or audio file for use in chat messages. Returns a `media_url` to include when sending a message via WebSocket. |

**Form Fields:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | ✅ | Image, video, or audio file |

**cURL Example:**
```bash
curl -X POST http://localhost:8000/upload-media \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/image.jpg"
```

**Response — `200 OK`:**
```json
{
  "media_url": "/images/a1b2c3d4.jpg",
  "type": "image"
}
```

> 💡 Use the returned `media_url` and `type` when sending media messages over WebSocket.

---

## ℹ️ Chat — Message Info & Reactions

### 1. Get Message Info

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /msgs/{msg_id}/info` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get delivery and read status of a specific message. Only the sender or receiver can access this. |

**Response — `200 OK`:**
```json
{
  "message_id": 42,
  "delivered_at": "2 min ago",
  "read_at": "1 min ago",
  "is_read": true
}
```

---

### 2. Get Message Reactions

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /msgs/{msg_id}/msg_reaction_info` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get the list of users who reacted to a specific message and their reactions. |

**Response — `200 OK`:**
```json
[
  {
    "user_id": 2,
    "username": "jane_doe",
    "profile_pic": "jane_avatar.png",
    "reaction": "❤️"
  }
]
```

---

### 3. Get Shared Post Reactions

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /shared/{shared_id}/reactions` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Get reaction details for a shared post. Only sender or receiver of the share can view. |

**Response — `200 OK`:** Same structure as message reactions.

---

## 🗑️ Chat — Delete & Clear

### 1. Delete Message for Me

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /delete/for-me/{msg_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Hides a message from your view only. The other person can still see it. |

**Response — `200 OK`:**
```json
{
  "message_id": 42,
  "detail": "Deleted for you"
}
```

---

### 2. Delete Shared Post for Me

| Detail | Value |
|--------|-------|
| **Endpoint** | `POST /delete-share/for-me/{share_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Hides a shared post from your view only. |

**Response — `200 OK`:**
```json
{
  "share_id": 10,
  "detail": "Deleted for you"
}
```

---

### 3. Clear Entire Chat

| Detail | Value |
|--------|-------|
| **Endpoint** | `DELETE /clear-chat/{friend_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Clears all visible messages in a conversation from your view. Messages remain visible to the other person. |

**Response — `200 OK`:**
```json
{
  "detail": "Chat cleared successfully"
}
```

---

## ✏️ Chat — Edit Messages

### 1. Check If Message Is Editable

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /msg/{msg_id}/can_edit` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Check whether a message can still be edited. Messages can only be edited within a configured time window (default: 15 minutes) after sending. |

**Response — `200 OK`:**
```json
{
  "can_edit": true,
  "message": null
}
```

> If the time window has passed:
> ```json
> { "can_edit": false, "message": null }
> ```

---

## 📜 Chat — History

### 1. Get Chat History

| Detail | Value |
|--------|-------|
| **Endpoint** | `GET /chat/history/{friend_id}` |
| **Auth** | 🔐 Bearer Token |
| **Description** | Retrieve the full conversation history with a friend — both messages and shared posts, excluding deleted items. |

**Response — `200 OK`:**
Returns a combined list of messages and shared posts, sorted by timestamp. Each item includes:

**Message item:**
```json
{
  "type": "message",
  "id": 42,
  "content": "Hey! How are you?",
  "sender_id": 1,
  "receiver_id": 2,
  "media_type": null,
  "media_url": null,
  "timestamp": "5 min ago",
  "is_edited": false,
  "reaction_count": 1,
  "reactions": "❤️",
  "is_read": true,
  "is_reply": false
}
```

**Shared post item:**
```json
{
  "type": "shared_post",
  "shared_id": 10,
  "post_id": 5,
  "title": "Sunset vibes 🌅",
  "from_user_id": 1,
  "to_user_id": 2,
  "media_type": "image",
  "media_url": "sunset.jpg",
  "sender_id": 1,
  "message": "Look at this!",
  "reactions": "🔥",
  "timestamp": "10 min ago"
}
```

> Reply messages include `is_reply: true` and a `reply_to` object with the original message or shared post details.

---

## ⚡ WebSocket — Real-Time Chat

The heart of the chat system. All real-time features (messaging, typing indicators, reactions, edits, deletes) flow through a single WebSocket connection.

### Connecting

| Detail | Value |
|--------|-------|
| **Endpoint** | `ws://localhost:8000/chat/ws/{user_id}?token=<your_jwt_token>` |
| **Protocol** | WebSocket |
| **Auth** | JWT token passed as query parameter |
| **Description** | Opens a persistent real-time connection. On connect, any missed (unread) messages and shared posts are automatically delivered. |

**Example — Postman:**
1. Open a new **WebSocket Request** tab.
2. Enter: `ws://localhost:8000/chat/ws/1?token=<your_access_token>`
3. Click **Connect**.

**Example — JavaScript:**
```javascript
const ws = new WebSocket("ws://localhost:8000/chat/ws/1?token=YOUR_JWT_TOKEN");

ws.onopen = () => console.log("Connected!");
ws.onmessage = (event) => console.log("Received:", JSON.parse(event.data));
ws.onclose = () => console.log("Disconnected");
```

> ⚠️ The `user_id` in the URL **must match** the user ID encoded in the JWT token. Mismatches are rejected.

---

### Message Types — Sending

All messages are sent as **JSON strings** through the WebSocket. The `type` field determines the action.

#### 1. Send a Direct Message (Text or Media)

```json
{
  "to": 2,
  "content": "Hello Jane!",
  "media_url": null,
  "media_type": null
}
```

| Field | Type | Notes |
|-------|------|-------|
| `to` | int | Receiver's user ID |
| `content` | string | Message text |
| `media_url` | string/null | URL from `/upload-media` (if sending media) |
| `media_type` | string/null | `"image"`, `"video"`, `"audio"`, or `null` |

> 📌 No `type` field needed — a message without a `type` is treated as a regular DM.

---

#### 2. Reply to a Message

```json
{
  "type": "reply_message",
  "to": 2,
  "content": "I agree!",
  "reply_msg_id": 42,
  "media_url": null,
  "media_type": null
}
```

---

#### 3. Reply to a Shared Post

```json
{
  "type": "reply_to_share",
  "to": 2,
  "content": "This post is amazing!",
  "reply_share_id": 10,
  "media_url": null,
  "media_type": null
}
```

---

#### 4. Edit a Message

```json
{
  "type": "edit_message",
  "msg_id": 42,
  "new_content": "Updated message text",
  "receiver_id": 2
}
```

> ⏱️ Editing is only allowed within the configured time window (default: 15 min). Use `GET /msg/{msg_id}/can_edit` to check.

---

#### 5. Delete Message for Everyone

```json
{
  "type": "delete_for_everyone",
  "message_id": 42,
  "receiver_id": 2
}
```

> Only the **sender** can delete for everyone. Both parties receive instant notification.

---

#### 6. Delete Shared Post for Everyone

```json
{
  "type": "delete_share_for_everyone",
  "message_id": 10,
  "receiver_id": 2
}
```

---

#### 7. React to a Message (Emoji)

```json
{
  "type": "reaction",
  "message_id": 42,
  "reaction": "❤️"
}
```

> **Toggle behavior:** Sending the same emoji again removes the reaction. Sending a different emoji switches it.

---

#### 8. React to a Shared Post

```json
{
  "type": "shared_post_reaction",
  "shared_post_id": 10,
  "reaction": "🔥"
}
```

---

#### 9. Typing Indicator

```json
{
  "type": "typing",
  "receiver_id": 2,
  "is_typing": true
}
```

> Send `is_typing: false` when the user stops typing.

---

#### 10. Read Receipt

```json
{
  "type": "read_receipt",
  "sender_id": 2
}
```

> Marks **all** unread messages from `sender_id` as read. The sender receives a real-time notification.

---

#### 11. Pong (Heartbeat Response)

```json
{
  "type": "pong"
}
```

> The server sends periodic `ping` messages. Respond with `pong` to signal you're still connected. Failure to respond may result in disconnection (zombie detection).

---

### Message Types — Receiving

You will receive various event payloads from the server:

| Event Type | Description |
|------------|-------------|
| Regular message | `{ "id", "content", "sender_id", "timestamp", "is_reply": false, ... }` |
| Reply message | Same as above with `"is_reply": true` + `"reply_to": { ... }` |
| `edit_message` | `{ "type": "edit_message", "message_id", "new_content", "is_edited" }` |
| `delete_message` | `{ "type": "delete_message", "message_id", "is_deleted_for_everyone": true }` |
| `reaction` | `{ "type": "reaction", "message_id", "reaction", "reaction_count", "reacted_by" }` |
| `reaction_update` | `{ "type": "reaction_update", "data": { ... } }` — for shared post reactions |
| `shared_post` | `{ "type": "shared_post", "shared_id", "post_id", "title", ... }` |
| `share_deleted` | `{ "type": "share_deleted", "share_id", "is_deleted_for_everyone": true }` |
| `typing` | `{ "type": "typing", "is_typing": true/false }` |
| `read_receipt` | `{ "type": "read_receipt", "reader_id", "read_at", ... }` |
| `ping` | Server heartbeat — respond with `{ "type": "pong" }` |

---

## 📊 Quick Reference — All Endpoints at a Glance

### REST API Endpoints (55 total)

| # | Method | Endpoint | Auth | Description |
|---|--------|----------|------|-------------|
| 1 | `GET` | `/health` | 🌐 | Health check |
| 2 | `POST` | `/user/signup` | 🌐 ⚡ | Register new user |
| 3 | `POST` | `/login` | 🌐 ⚡ | Log in, get JWT + refresh token |
| 4 | `POST` | `/refresh` | 🌐 ⚡ | Rotate refresh token |
| 5 | `POST` | `/logout` | 🔐 | Blacklist token + revoke refresh tokens |
| 6 | `POST` | `/forgot-password` | 🌐 ⚡ | Initiate unauthenticated password reset |
| 7 | `POST` | `/reset-password` (auth) | 🌐 ⚡ | Complete unauthenticated password reset |
| 8 | `GET` | `/users/getAllUsers` | 🌐 | List all users |
| 9 | `GET` | `/users/{id}/profile` | 🔐 | View user profile |
| 10 | `GET` | `/users/{id}/profile/pic` | 🔐 | Get user's profile pic |
| 11 | `GET` | `/users/{id}/posts` | 🔐 | Get user's posts |
| 12 | `GET` | `/users/{id}/followers` | 🔐 | List user's followers |
| 13 | `GET` | `/users/{id}/following` | 🔐 | List user's following |
| 14 | `GET` | `/me/profile` | 🔐 | My profile |
| 15 | `GET` | `/me/profile/pic` | 🔐 | My profile picture |
| 16 | `DELETE` | `/me/profilepic/delete` | 🔐 | Remove my profile pic |
| 17 | `PATCH` | `/me/updateInfo` | 🔐 | Update my info |
| 18 | `GET` | `/me/posts` | 🔐 | My posts (paginated) |
| 19 | `GET` | `/me/votedOnPosts` | 🔐 | Posts I voted on |
| 20 | `GET` | `/me/voteStats` | 🔐 | My vote statistics |
| 21 | `GET` | `/me/likedPosts` | 🔐 | Posts I liked |
| 22 | `GET` | `/me/dislikedPosts` | 🔐 | Posts I disliked |
| 23 | `GET` | `/me/commented-on` | 🔐 | Posts I commented on |
| 24 | `GET` | `/me/comment-stats` | 🔐 | My comment statistics |
| 25 | `GET` | `/me/notifications` | 🔐 | Paginated notifications |
| 26 | `GET` | `/me/notifications/unread-count` | 🔐 | Unread notification count |
| 27 | `PATCH` | `/me/notifications/read` | 🔐 | Mark all notifications read |
| 28 | `POST` | `/posts/createPost` | 🔐 ⚡ | Create post |
| 29 | `GET` | `/posts/getPost/{id}` | 🔐 | Get post detail |
| 30 | `PUT` | `/posts/editPost/{id}` | 🔐 | Edit post |
| 31 | `DELETE` | `/posts/deletePost/{id}` | 🔐 | Delete post |
| 32 | `POST` | `/comment` | 🔐 ⚡ | Create comment |
| 33 | `GET` | `/comments-on/{post_id}` | 🔐 | Get comments on post |
| 34 | `PATCH` | `/comments/edit_comment/{id}` | 🔐 | Edit comment |
| 35 | `DELETE` | `/comments/delete_comment/{id}` | 🔐 | Delete comment |
| 36 | `POST` | `/vote/on_post` | 🔐 | Vote on post |
| 37 | `POST` | `/vote/on_comment` | 🔐 | Vote on comment |
| 38 | `POST` | `/follow/{user_id}` | 🔐 ⚡ | Follow user |
| 39 | `DELETE` | `/unfollow/{user_id}` | 🔐 | Unfollow user |
| 40 | `DELETE` | `/remove_follower/{user_id}` | 🔐 | Remove follower |
| 41 | `GET` | `/feed/home` | 🔐 | Home feed |
| 42 | `GET` | `/feed/explore` | 🔐 | Explore feed |
| 43 | `GET` | `/search` | 🔐 | Search users/hashtags |
| 44 | `POST` | `/change-password` | 🔐 ⚡ | Request password OTP |
| 45 | `POST` | `/reset-password` (auth) | 🔐 ⚡ | Reset password with OTP |
| 46 | `GET` | `/recent-chats` | 🔐 | Recent conversations |
| 47 | `POST` | `/share` | 🔐 | Share post to DM |
| 48 | `POST` | `/upload-media` | 🔐 | Upload chat media |
| 49 | `GET` | `/chat/history/{friend_id}` | 🔐 | Chat history |
| 50 | `GET` | `/msgs/{msg_id}/info` | 🔐 | Message delivery info |
| 51 | `GET` | `/msgs/{msg_id}/msg_reaction_info` | 🔐 | Message reactions |
| 52 | `GET` | `/shared/{id}/reactions` | 🔐 | Shared post reactions |
| 53 | `POST` | `/delete/for-me/{msg_id}` | 🔐 | Delete message for me |
| 54 | `POST` | `/delete-share/for-me/{id}` | 🔐 | Delete share for me |
| 55 | `DELETE` | `/clear-chat/{friend_id}` | 🔐 | Clear chat |
| 56 | `GET` | `/msg/{msg_id}/can_edit` | 🔐 | Check edit eligibility |

> ⚡ = Rate-limited endpoint. See [FEATURES.md](./FEATURES.md) for default limits and `.env` configuration.

### WebSocket Endpoint

| # | Protocol | Endpoint | Auth | Description |
|---|----------|----------|------|-------------|
| 1 | `WS` | `/chat/ws/{user_id}?token=<jwt>` | 🔐 | Real-time chat + notifications |

### WebSocket Message Types (Send)

| # | Type | Description |
|---|------|-------------|
| 1 | *(no type)* | Send direct message |
| 2 | `reply_message` | Reply to a message |
| 3 | `reply_to_share` | Reply to a shared post |
| 4 | `edit_message` | Edit a sent message |
| 5 | `delete_for_everyone` | Delete message for everyone |
| 6 | `delete_share_for_everyone` | Delete shared post for everyone |
| 7 | `reaction` | React to a message (emoji) |
| 8 | `shared_post_reaction` | React to a shared post |
| 9 | `typing` | Typing indicator |
| 10 | `read_receipt` | Mark messages as read |
| 11 | `pong` | Heartbeat response |

---

## 💡 Tips & Troubleshooting

- **Getting `401 Unauthorized`?** Your access token may have expired. Use `POST /refresh` with your refresh token to get a new one silently — no re-login needed.
- **Getting `429 Too Many Requests`?** You've hit a rate limit. Check the `Retry-After` header for when you can try again.
- **Getting `404 Not Found` for media?** Ensure the Docker volumes are mounted and the folders (`profilepics/`, `posts_media/`, `chat-media/`) exist.
- **WebSocket disconnecting?** Make sure to respond to `ping` messages with `pong` to avoid zombie detection.
- **Swagger UI** at `http://localhost:8000/docs` is the fastest way to test REST endpoints — it handles auth and request formatting for you.
- **For WebSocket testing**, use **Postman** (WebSocket tab), the **[websocat](https://github.com/nickel-org/websocat)** CLI tool, or the browser DevTools console.
- **Rate limits on edit**: Message editing is time-limited (default 15 minutes). Always check `/msg/{msg_id}/can_edit` first.
- **Refresh token reuse is dangerous**: If you reuse an old refresh token after rotation, the entire token family is revoked as a security measure.

---

> Built with ❤️ using FastAPI, SQLAlchemy, PostgreSQL, Redis & WebSockets