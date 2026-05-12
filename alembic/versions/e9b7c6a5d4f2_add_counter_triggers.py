"""add counter triggers

Revision ID: e9b7c6a5d4f2
Revises: d8a5f4b7c2e1
Create Date: 2026-05-06 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e9b7c6a5d4f2"
down_revision: Union[str, Sequence[str], None] = "d8a5f4b7c2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_post_vote_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.action THEN
                    UPDATE posts SET likes = likes + 1 WHERE id = NEW.post_id;
                ELSE
                    UPDATE posts SET dis_likes = dis_likes + 1 WHERE id = NEW.post_id;
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.action THEN
                    UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id = OLD.post_id;
                ELSE
                    UPDATE posts SET dis_likes = GREATEST(dis_likes - 1, 0) WHERE id = OLD.post_id;
                END IF;
            ELSIF TG_OP = 'UPDATE' AND OLD.action IS DISTINCT FROM NEW.action THEN
                IF OLD.action THEN
                    UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id = OLD.post_id;
                ELSE
                    UPDATE posts SET dis_likes = GREATEST(dis_likes - 1, 0) WHERE id = OLD.post_id;
                END IF;

                IF NEW.action THEN
                    UPDATE posts SET likes = likes + 1 WHERE id = NEW.post_id;
                ELSE
                    UPDATE posts SET dis_likes = dis_likes + 1 WHERE id = NEW.post_id;
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS votes_sync_post_counts ON votes;
        CREATE TRIGGER votes_sync_post_counts
        AFTER INSERT OR UPDATE OF action OR DELETE ON votes
        FOR EACH ROW EXECUTE FUNCTION trg_sync_post_vote_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_comment_vote_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW."like" THEN
                    UPDATE comments SET likes = likes + 1 WHERE id = NEW.comment_id;
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD."like" THEN
                    UPDATE comments SET likes = GREATEST(likes - 1, 0) WHERE id = OLD.comment_id;
                END IF;
            ELSIF TG_OP = 'UPDATE' AND OLD."like" IS DISTINCT FROM NEW."like" THEN
                IF OLD."like" THEN
                    UPDATE comments SET likes = GREATEST(likes - 1, 0) WHERE id = OLD.comment_id;
                END IF;
                IF NEW."like" THEN
                    UPDATE comments SET likes = likes + 1 WHERE id = NEW.comment_id;
                END IF;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS comment_votes_sync_comment_counts ON comment_votes;
        CREATE TRIGGER comment_votes_sync_comment_counts
        AFTER INSERT OR UPDATE OF "like" OR DELETE ON comment_votes
        FOR EACH ROW EXECUTE FUNCTION trg_sync_comment_vote_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_post_comment_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE posts SET comments_cnt = comments_cnt + 1 WHERE id = NEW.post_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE posts SET comments_cnt = GREATEST(comments_cnt - 1, 0) WHERE id = OLD.post_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS comments_sync_post_counts ON comments;
        CREATE TRIGGER comments_sync_post_counts
        AFTER INSERT OR DELETE ON comments
        FOR EACH ROW EXECUTE FUNCTION trg_sync_post_comment_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_post_view_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE posts SET views = views + 1 WHERE id = NEW.post_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE posts SET views = GREATEST(views - 1, 0) WHERE id = OLD.post_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS post_views_sync_post_counts ON post_views;
        CREATE TRIGGER post_views_sync_post_counts
        AFTER INSERT OR DELETE ON post_views
        FOR EACH ROW EXECUTE FUNCTION trg_sync_post_view_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_connection_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE users SET following_cnt = following_cnt + 1 WHERE id = NEW.follower_id;
                UPDATE users SET followers_cnt = followers_cnt + 1 WHERE id = NEW.followed_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE users SET following_cnt = GREATEST(following_cnt - 1, 0) WHERE id = OLD.follower_id;
                UPDATE users SET followers_cnt = GREATEST(followers_cnt - 1, 0) WHERE id = OLD.followed_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS connections_sync_user_counts ON connections;
        CREATE TRIGGER connections_sync_user_counts
        AFTER INSERT OR DELETE ON connections
        FOR EACH ROW EXECUTE FUNCTION trg_sync_connection_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_message_reaction_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE messages SET reaction_cnt = reaction_cnt + 1 WHERE id = NEW.message_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE messages SET reaction_cnt = GREATEST(reaction_cnt - 1, 0) WHERE id = OLD.message_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS message_reactions_sync_message_counts ON message_reactions;
        CREATE TRIGGER message_reactions_sync_message_counts
        AFTER INSERT OR DELETE ON message_reactions
        FOR EACH ROW EXECUTE FUNCTION trg_sync_message_reaction_counts();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_sync_shared_post_reaction_counts()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE shared_posts SET reaction_cnt = reaction_cnt + 1 WHERE id = NEW.shared_post_id;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE shared_posts SET reaction_cnt = GREATEST(reaction_cnt - 1, 0) WHERE id = OLD.shared_post_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS shared_post_reactions_sync_share_counts ON shared_post_reactions;
        CREATE TRIGGER shared_post_reactions_sync_share_counts
        AFTER INSERT OR DELETE ON shared_post_reactions
        FOR EACH ROW EXECUTE FUNCTION trg_sync_shared_post_reaction_counts();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS shared_post_reactions_sync_share_counts ON shared_post_reactions")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_shared_post_reaction_counts()")
    op.execute("DROP TRIGGER IF EXISTS message_reactions_sync_message_counts ON message_reactions")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_message_reaction_counts()")
    op.execute("DROP TRIGGER IF EXISTS connections_sync_user_counts ON connections")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_connection_counts()")
    op.execute("DROP TRIGGER IF EXISTS post_views_sync_post_counts ON post_views")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_post_view_counts()")
    op.execute("DROP TRIGGER IF EXISTS comments_sync_post_counts ON comments")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_post_comment_counts()")
    op.execute("DROP TRIGGER IF EXISTS comment_votes_sync_comment_counts ON comment_votes")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_comment_vote_counts()")
    op.execute("DROP TRIGGER IF EXISTS votes_sync_post_counts ON votes")
    op.execute("DROP FUNCTION IF EXISTS trg_sync_post_vote_counts()")
