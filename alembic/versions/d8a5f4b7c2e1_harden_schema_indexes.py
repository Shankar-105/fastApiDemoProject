"""harden schema indexes

Revision ID: d8a5f4b7c2e1
Revises: b2c1e7d3f901
Create Date: 2026-05-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8a5f4b7c2e1"
down_revision: Union[str, Sequence[str], None] = "b2c1e7d3f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_check(table: str, name: str, expression: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{name}'
                  AND conrelid = '{table}'::regclass
            ) THEN
                ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression});
            END IF;
        END $$;
        """
    )


def _add_unique(table: str, name: str, columns: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{name}'
                  AND conrelid = '{table}'::regclass
            ) THEN
                ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({columns});
            END IF;
        END $$;
        """
    )


def _drop_constraint(table: str, name: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE notificationtype AS ENUM ('like', 'comment', 'follow');
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type notificationtype NOT NULL,
            entity_id INTEGER NULL,
            entity_type VARCHAR NULL,
            text VARCHAR NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )

    # Clean clearly broken rows before tightening columns the app already
    # treats as required.
    op.execute("DELETE FROM connections WHERE followed_id = follower_id")
    op.execute(
        """
        DELETE FROM shared_posts
        WHERE post_id IS NULL
           OR from_user_id IS NULL
           OR to_user_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM deleted_shared_posts
        WHERE user_id IS NULL
           OR shared_post_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM deleted_shared_posts keep
        USING deleted_shared_posts dup
        WHERE keep.id > dup.id
          AND keep.user_id = dup.user_id
          AND keep.shared_post_id = dup.shared_post_id
        """
    )
    op.execute("DELETE FROM otps WHERE email IS NULL")

    op.execute(
        """
        UPDATE posts
        SET likes = GREATEST(COALESCE(likes, 0), 0),
            dis_likes = GREATEST(COALESCE(dis_likes, 0), 0),
            views = GREATEST(COALESCE(views, 0), 0),
            comments_cnt = GREATEST(COALESCE(comments_cnt, 0), 0)
        """
    )
    op.execute(
        """
        UPDATE comments
        SET likes = GREATEST(COALESCE(likes, 0), 0),
            created_at = COALESCE(created_at, now())
        """
    )
    op.execute(
        """
        UPDATE users
        SET followers_cnt = GREATEST(COALESCE(followers_cnt, 0), 0),
            following_cnt = GREATEST(COALESCE(following_cnt, 0), 0)
        """
    )
    op.execute(
        """
        UPDATE messages
        SET created_at = COALESCE(created_at, now()),
            is_read = COALESCE(is_read, false),
            is_deleted_for_everyone = COALESCE(is_deleted_for_everyone, false),
            is_edited = COALESCE(is_edited, false),
            reaction_cnt = GREATEST(COALESCE(reaction_cnt, 0), 0),
            is_reply_msg = COALESCE(is_reply_msg, false),
            is_reply_to_share = COALESCE(is_reply_to_share, false)
        """
    )
    op.execute(
        """
        UPDATE shared_posts
        SET created_at = COALESCE(created_at, now()),
            is_read = COALESCE(is_read, false),
            is_deleted_for_everyone = COALESCE(is_deleted_for_everyone, false),
            reaction_cnt = GREATEST(COALESCE(reaction_cnt, 0), 0)
        """
    )
    op.execute("UPDATE notifications SET created_at = COALESCE(created_at, now()), is_read = COALESCE(is_read, false)")
    op.execute("UPDATE refresh_tokens SET created_at = COALESCE(created_at, now()), revoked = COALESCE(revoked, false)")

    op.alter_column("otps", "email", existing_type=sa.String(), nullable=False)
    op.alter_column("posts", "views", existing_type=sa.Integer(), server_default=sa.text("0"), nullable=False)
    op.alter_column("posts", "comments_cnt", existing_type=sa.Integer(), server_default=sa.text("0"), nullable=False)
    op.alter_column("comments", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("shared_posts", "post_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("shared_posts", "from_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("shared_posts", "to_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("shared_posts", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    op.alter_column("shared_posts", "is_read", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("shared_posts", "is_deleted_for_everyone", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("shared_posts", "reaction_cnt", existing_type=sa.Integer(), server_default=sa.text("0"), nullable=False)
    op.alter_column("deleted_shared_posts", "user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("deleted_shared_posts", "shared_post_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("messages", "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("messages", "is_read", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("messages", "is_deleted_for_everyone", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("messages", "is_edited", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("messages", "reaction_cnt", existing_type=sa.Integer(), server_default=sa.text("0"), nullable=False)
    op.alter_column("messages", "is_reply_msg", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("messages", "is_reply_to_share", existing_type=sa.Boolean(), server_default=sa.text("false"), nullable=False)
    op.alter_column("notifications", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    op.alter_column("refresh_tokens", "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)

    _add_unique("deleted_shared_posts", "uq_user_deleted_shared_post", "user_id, shared_post_id")

    _add_check("connections", "ck_connections_no_self_follow", "followed_id <> follower_id")
    _add_check("posts", "ck_posts_likes_nonnegative", "likes >= 0")
    _add_check("posts", "ck_posts_dislikes_nonnegative", "dis_likes >= 0")
    _add_check("posts", "ck_posts_views_nonnegative", "views >= 0")
    _add_check("posts", "ck_posts_comments_cnt_nonnegative", "comments_cnt >= 0")
    _add_check("posts", "ck_posts_media_type_valid", "(media_type IS NULL) OR (media_type IN ('image', 'video'))")
    _add_check("comments", "ck_comments_likes_nonnegative", "likes >= 0")
    _add_check("users", "ck_users_followers_cnt_nonnegative", "followers_cnt >= 0")
    _add_check("users", "ck_users_following_cnt_nonnegative", "following_cnt >= 0")
    _add_check("messages", "ck_messages_reaction_cnt_nonnegative", "reaction_cnt >= 0")
    _add_check("messages", "ck_messages_media_type_valid", "(media_type IS NULL) OR (media_type IN ('false', 'image', 'video', 'audio'))")
    _add_check("shared_posts", "ck_shared_posts_reaction_cnt_nonnegative", "reaction_cnt >= 0")
    _add_check("notifications", "ck_notifications_entity_type_valid", "(entity_type IS NULL) OR (entity_type IN ('post', 'comment'))")

    op.execute("CREATE INDEX IF NOT EXISTS ix_connections_follower_followed ON connections (follower_id, followed_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_post_replies_shared_post_id ON shared_post_replies (shared_post_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_posts_from_to_created ON shared_posts (from_user_id, to_user_id, created_at) WHERE is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_posts_to_from_created ON shared_posts (to_user_id, from_user_id, created_at) WHERE is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_posts_unread_inbox ON shared_posts (to_user_id, created_at) WHERE is_read = false AND is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_posts_post_id ON shared_posts (post_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_deleted_messages_message_id ON deleted_messages (message_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_deleted_shared_posts_shared_post_id ON deleted_shared_posts (shared_post_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_otps_expires_at ON otps (expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_votes_user_action_post ON votes (user_id, action, post_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_comment_votes_user_comment ON comment_votes (user_id, comment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_comments_post_created ON comments (post_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_comments_user_post ON comments (user_id, post_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_posts_user_created ON posts (user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_posts_created_at ON posts (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_posts_likes_created ON posts (likes, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_saved_posts_user_created ON saved_posts (user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_post_views_user_id ON post_views (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_post_views_viewed_at ON post_views (viewed_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_message_replies_original_id ON message_replies (original_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_sender_receiver_created ON messages (sender_id, receiver_id, created_at) WHERE is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_receiver_sender_created ON messages (receiver_id, sender_id, created_at) WHERE is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_unread_receiver_created ON messages (receiver_id, created_at) WHERE is_read = false AND is_deleted_for_everyone = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_message_reactions_user_id ON message_reactions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_shared_post_reactions_user_id ON shared_post_reactions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_owner_created ON notifications (owner_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_actor_id ON notifications (actor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_unread_owner_created ON notifications (owner_id, created_at) WHERE is_read = false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_revoked ON refresh_tokens (user_id, revoked)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_expires_at ON refresh_tokens (expires_at)")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ux_users_email_lower'
            ) THEN
                IF EXISTS (
                    SELECT 1
                    FROM users
                    WHERE email IS NOT NULL
                    GROUP BY lower(email)
                    HAVING count(*) > 1
                ) THEN
                    CREATE INDEX IF NOT EXISTS ix_users_email_lower_nonunique
                    ON users (lower(email))
                    WHERE email IS NOT NULL;
                ELSE
                    CREATE UNIQUE INDEX ux_users_email_lower
                    ON users (lower(email))
                    WHERE email IS NOT NULL;
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower_nonunique")
    op.execute("DROP INDEX IF EXISTS ux_users_email_lower")
    op.execute("DROP INDEX IF EXISTS ix_refresh_tokens_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_refresh_tokens_user_revoked")
    op.execute("DROP INDEX IF EXISTS ix_notifications_unread_owner_created")
    op.execute("DROP INDEX IF EXISTS ix_notifications_actor_id")
    op.execute("DROP INDEX IF EXISTS ix_notifications_owner_created")
    op.execute("DROP INDEX IF EXISTS ix_shared_post_reactions_user_id")
    op.execute("DROP INDEX IF EXISTS ix_message_reactions_user_id")
    op.execute("DROP INDEX IF EXISTS ix_messages_unread_receiver_created")
    op.execute("DROP INDEX IF EXISTS ix_messages_receiver_sender_created")
    op.execute("DROP INDEX IF EXISTS ix_messages_sender_receiver_created")
    op.execute("DROP INDEX IF EXISTS ix_message_replies_original_id")
    op.execute("DROP INDEX IF EXISTS ix_post_views_viewed_at")
    op.execute("DROP INDEX IF EXISTS ix_post_views_user_id")
    op.execute("DROP INDEX IF EXISTS ix_saved_posts_user_created")
    op.execute("DROP INDEX IF EXISTS ix_posts_likes_created")
    op.execute("DROP INDEX IF EXISTS ix_posts_created_at")
    op.execute("DROP INDEX IF EXISTS ix_posts_user_created")
    op.execute("DROP INDEX IF EXISTS ix_comments_user_post")
    op.execute("DROP INDEX IF EXISTS ix_comments_post_created")
    op.execute("DROP INDEX IF EXISTS ix_comment_votes_user_comment")
    op.execute("DROP INDEX IF EXISTS ix_votes_user_action_post")
    op.execute("DROP INDEX IF EXISTS ix_otps_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_deleted_shared_posts_shared_post_id")
    op.execute("DROP INDEX IF EXISTS ix_deleted_messages_message_id")
    op.execute("DROP INDEX IF EXISTS ix_shared_posts_post_id")
    op.execute("DROP INDEX IF EXISTS ix_shared_posts_unread_inbox")
    op.execute("DROP INDEX IF EXISTS ix_shared_posts_to_from_created")
    op.execute("DROP INDEX IF EXISTS ix_shared_posts_from_to_created")
    op.execute("DROP INDEX IF EXISTS ix_shared_post_replies_shared_post_id")
    op.execute("DROP INDEX IF EXISTS ix_connections_follower_followed")

    _drop_constraint("notifications", "ck_notifications_entity_type_valid")
    _drop_constraint("shared_posts", "ck_shared_posts_reaction_cnt_nonnegative")
    _drop_constraint("messages", "ck_messages_media_type_valid")
    _drop_constraint("messages", "ck_messages_reaction_cnt_nonnegative")
    _drop_constraint("users", "ck_users_following_cnt_nonnegative")
    _drop_constraint("users", "ck_users_followers_cnt_nonnegative")
    _drop_constraint("comments", "ck_comments_likes_nonnegative")
    _drop_constraint("posts", "ck_posts_media_type_valid")
    _drop_constraint("posts", "ck_posts_comments_cnt_nonnegative")
    _drop_constraint("posts", "ck_posts_views_nonnegative")
    _drop_constraint("posts", "ck_posts_dislikes_nonnegative")
    _drop_constraint("posts", "ck_posts_likes_nonnegative")
    _drop_constraint("connections", "ck_connections_no_self_follow")
    _drop_constraint("deleted_shared_posts", "uq_user_deleted_shared_post")

    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notificationtype")
