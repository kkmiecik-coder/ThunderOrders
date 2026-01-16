"""Add feedback system tables

Revision ID: a511c0a36dad
Revises: d8e9f0a1b2c3
Create Date: 2026-01-16 20:49:04.387651

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a511c0a36dad'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    # Create feedback_surveys table
    op.create_table('feedback_surveys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('token', sa.String(length=100), nullable=False),
        sa.Column('status', sa.Enum('draft', 'active', 'closed', name='feedback_survey_status'), nullable=False),
        sa.Column('closes_at', sa.DateTime(), nullable=True),
        sa.Column('is_anonymous', sa.Boolean(), nullable=True),
        sa.Column('allow_multiple_responses', sa.Boolean(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_feedback_surveys_status', 'feedback_surveys', ['status'], unique=False)
    op.create_index('ix_feedback_surveys_token', 'feedback_surveys', ['token'], unique=True)

    # Create feedback_questions table
    op.create_table('feedback_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), nullable=False),
        sa.Column('question_type', sa.Enum('section_header', 'text', 'rating_scale', 'rating_10', 'emoji_rating', 'yes_no', 'yes_no_comment', 'multiple_choice', 'checkbox_list', 'textarea', name='feedback_question_type'), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('options', sa.JSON(), nullable=True),
        sa.Column('is_required', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['survey_id'], ['feedback_surveys.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_feedback_questions_survey_id', 'feedback_questions', ['survey_id'], unique=False)

    # Create feedback_responses table
    op.create_table('feedback_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['survey_id'], ['feedback_surveys.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_feedback_responses_survey_id', 'feedback_responses', ['survey_id'], unique=False)
    op.create_index('ix_feedback_responses_user_id', 'feedback_responses', ['user_id'], unique=False)

    # Create feedback_answers table
    op.create_table('feedback_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('response_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('answer_value', sa.String(length=255), nullable=True),
        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('answer_options', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['question_id'], ['feedback_questions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['response_id'], ['feedback_responses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_feedback_answers_question_id', 'feedback_answers', ['question_id'], unique=False)
    op.create_index('ix_feedback_answers_response_id', 'feedback_answers', ['response_id'], unique=False)


def downgrade():
    # Drop feedback_answers
    op.drop_index('ix_feedback_answers_response_id', table_name='feedback_answers')
    op.drop_index('ix_feedback_answers_question_id', table_name='feedback_answers')
    op.drop_table('feedback_answers')

    # Drop feedback_responses
    op.drop_index('ix_feedback_responses_user_id', table_name='feedback_responses')
    op.drop_index('ix_feedback_responses_survey_id', table_name='feedback_responses')
    op.drop_table('feedback_responses')

    # Drop feedback_questions
    op.drop_index('ix_feedback_questions_survey_id', table_name='feedback_questions')
    op.drop_table('feedback_questions')

    # Drop feedback_surveys
    op.drop_index('ix_feedback_surveys_token', table_name='feedback_surveys')
    op.drop_index('ix_feedback_surveys_status', table_name='feedback_surveys')
    op.drop_table('feedback_surveys')

    # Drop ENUMs
    op.execute("DROP TYPE IF EXISTS feedback_question_type")
    op.execute("DROP TYPE IF EXISTS feedback_survey_status")
