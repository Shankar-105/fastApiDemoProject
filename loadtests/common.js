import http from "k6/http";
import { check, group } from "k6";

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

const TEST_USER = {
  username: __ENV.LOADTEST_USERNAME || "k6_load_user",
  email: __ENV.LOADTEST_EMAIL || "k6.load.user@example.com",
  password: __ENV.LOADTEST_PASSWORD || "K6Load@123",
};

function makeAuthHeaders(token) {
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

function signupTestUser() {
  const payload = JSON.stringify({
    username: TEST_USER.username,
    email: TEST_USER.email,
    password: TEST_USER.password,
    nickname: "k6-user",
  });

  const res = http.post(`${BASE_URL}/user/signup`, payload, {
    headers: { "Content-Type": "application/json" },
    responseCallback: http.expectedStatuses(201, 409, 422, 429, 500),
    tags: { endpoint: "user_signup" },
  });

  check(res, {
    "signup endpoint reachable": (r) => [201, 409, 422, 429, 500].includes(r.status),
  });
}

function tryLoginForToken() {
  const body = `username=${encodeURIComponent(TEST_USER.username)}&password=${encodeURIComponent(TEST_USER.password)}`;

  const res = http.post(`${BASE_URL}/login`, body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    responseCallback: http.expectedStatuses(202, 401, 403, 422, 429),
    tags: { endpoint: "auth_login" },
  });

  check(res, {
    "login endpoint reachable": (r) => [202, 401, 403, 422, 429].includes(r.status),
  });

  if (res.status === 202) {
    try {
      const parsed = res.json();
      return parsed.accessToken || null;
    } catch {
      return null;
    }
  }
  return null;
}

export function setupContext() {
  let token = tryLoginForToken();
  if (!token) {
    signupTestUser();
    token = tryLoginForToken();
  }
  return {
    token,
    testUser: TEST_USER,
    baseUrl: BASE_URL,
  };
}

function hitHealth() {
  const res = http.get(`${BASE_URL}/health`, {
    responseCallback: http.expectedStatuses(200),
    tags: { endpoint: "health" },
  });

  check(res, {
    "health status is 200": (r) => r.status === 200,
  });
}

function hitUsersAll() {
  const res = http.get(`${BASE_URL}/users/getAllUsers`, {
    responseCallback: http.expectedStatuses(201, 500),
    tags: { endpoint: "users_all" },
  });

  check(res, {
    "users/getAllUsers reachable": (r) => [201, 500].includes(r.status),
  });
}

function hitFeedExplore(token) {
  const res = http.get(`${BASE_URL}/feed/explore?page=1&limit=10`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429),
    tags: { endpoint: "feed_explore" },
  });

  check(res, {
    "feed/explore reachable": (r) => [200, 401, 403, 429].includes(r.status),
  });
}

function hitSearch(token) {
  const res = http.get(`${BASE_URL}/search?q=dev&limit=5&offset=0`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(202, 400, 401, 403, 429, 500),
    tags: { endpoint: "search" },
  });

  check(res, {
    "search reachable": (r) => [202, 400, 401, 403, 429, 500].includes(r.status),
  });
}

function hitUserPosts(token) {
  const res = http.get(`${BASE_URL}/users/1/posts?limit=5&offset=0`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 404, 429, 500),
    tags: { endpoint: "users_posts" },
  });

  check(res, {
    "users/{id}/posts reachable": (r) => [200, 401, 403, 404, 429, 500].includes(r.status),
  });
}

function hitNotifications(token) {
  const res = http.get(`${BASE_URL}/me/notifications/unread-count`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429),
    tags: { endpoint: "notifications_unread" },
  });

  check(res, {
    "notifications/unread-count reachable": (r) => [200, 401, 403, 429].includes(r.status),
  });
}

function hitPostDetails(token) {
  const res = http.get(`${BASE_URL}/posts/getPost/1`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 404, 429, 500),
    tags: { endpoint: "post_get" },
  });

  check(res, {
    "posts/getPost reachable": (r) => [200, 401, 403, 404, 429, 500].includes(r.status),
  });
}

function hitFeedHome(token) {
  const res = http.get(`${BASE_URL}/feed/home?limit=10&offset=0`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429, 500),
    tags: { endpoint: "feed_home" },
  });

  check(res, {
    "feed/home reachable": (r) => [200, 401, 403, 429, 500].includes(r.status),
  });
}

function hitMePosts(token) {
  const res = http.get(`${BASE_URL}/me/posts?limit=10&offset=0`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429, 500),
    tags: { endpoint: "me_posts" },
  });

  check(res, {
    "me/posts reachable": (r) => [200, 401, 403, 429, 500].includes(r.status),
  });
}

function hitUserProfile(token) {
  const res = http.get(`${BASE_URL}/users/1/profile`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 404, 429, 500),
    tags: { endpoint: "user_profile" },
  });

  check(res, {
    "users/{id}/profile reachable": (r) => [200, 401, 403, 404, 429, 500].includes(r.status),
  });
}

function hitCommentStats(token) {
  const res = http.get(`${BASE_URL}/me/comment-stats`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429, 500),
    tags: { endpoint: "me_comment_stats" },
  });

  check(res, {
    "me/comment-stats reachable": (r) => [200, 401, 403, 429, 500].includes(r.status),
  });
}

function hitVoteStats(token) {
  const res = http.get(`${BASE_URL}/me/voteStats`, {
    headers: makeAuthHeaders(token),
    responseCallback: http.expectedStatuses(200, 401, 403, 429, 500),
    tags: { endpoint: "me_vote_stats" },
  });

  check(res, {
    "me/voteStats reachable": (r) => [200, 401, 403, 429, 500].includes(r.status),
  });
}

export function runMixedScenario(data) {
  group("public-and-auth-mixed-flow", () => {
    hitHealth();
    hitUsersAll();

    hitFeedHome(data.token);
    hitFeedExplore(data.token);
    hitSearch(data.token);
    hitUserProfile(data.token);
    hitUserPosts(data.token);
    hitMePosts(data.token);
    hitVoteStats(data.token);
    hitCommentStats(data.token);
    hitNotifications(data.token);
    hitPostDetails(data.token);
  });
}
