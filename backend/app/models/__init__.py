"""Import all models so SQLAlchemy can resolve relationship references."""
from app.models.user import User  # noqa: F401
from app.models.model_config import ModelConfig  # noqa: F401
from app.models.knowledge_base import KnowledgeBase  # noqa: F401
from app.models.document import Document, DocumentChunk  # noqa: F401
from app.models.chat_history import ChatConversation, ChatMessage  # noqa: F401
from app.models.database_source import DatabaseSource, DatabaseSyncRun  # noqa: F401
from app.models.published_app import PublishedApp  # noqa: F401
from app.models.web_source import WebSource  # noqa: F401
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceKnowledgeBase, WorkspaceModelConfig, WorkspaceInvitation  # noqa: F401
from app.models.operation_log import OperationLog  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.user_memory import UserMemory  # noqa: F401
from app.models.user_profile import UserProfile  # noqa: F401
from app.models.channel import Channel  # noqa: F401
from app.models.channel_session import ChannelSession  # noqa: F401
from app.models.channel_schedule import ChannelSchedule  # noqa: F401
from app.models.mcp_server import McpServerConfig  # noqa: F401
from app.models.skill import Skill  # noqa: F401
from app.models.skill_install import SkillInstall  # noqa: F401
from app.models.skill_chain import SkillChain  # noqa: F401
from app.models.automation import AutomationTask, AutomationLog  # noqa: F401
from app.models.agent_config import AgentConfig  # noqa: F401
from app.models.device import Device  # noqa: F401
from app.models.prompt_template import PromptTemplate  # noqa: F401
from app.models.user_quota import UserQuota, UsageLog  # noqa: F401
from app.models.compiled_article import CompiledArticle, ArticleCrossRef  # noqa: F401
from app.models.health_report import HealthReport  # noqa: F401
from app.models.trajectory import RAGTrajectory  # noqa: F401
from app.models.entity_triple import EntityTriple  # noqa: F401
