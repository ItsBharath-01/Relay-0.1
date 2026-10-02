import os
import aiofiles
from typing import Dict, Any, List, Optional, Tuple, Union
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)

MAX_CONTENT_CHARS = 8000


class LocalFilesystemTool(BaseTool):
    tool_type: str = "local"
    id: str = "local_filesystem"
    name: str = "Local Filesystem"
    description: str = "Read files from the configured local workspace."
    provides: List[str] = ["file_read"]
    requires_connection: Optional[str] = None
    required_permissions: List[str] = []

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="file_read",
                capability_id="file_read",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="path",
                required_permission=None,
                param_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative file path inside workspace"}
                    },
                    "required": ["path"]
                },
                supports_idempotency_key=False
            )
        ]

    def _get_workspace_root(self) -> str:
        base_dir = os.environ.get("RELAY_WORKSPACE_ROOT")
        if not base_dir:
            base_dir = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)
        return os.path.abspath(base_dir)

    def _secure_resolve_path(self, file_path: str) -> Optional[str]:
        root = os.path.realpath(self._get_workspace_root())
        if not file_path or not isinstance(file_path, str):
            return None
        if os.path.isabs(file_path):
            return None
            
        target = os.path.abspath(os.path.join(root, file_path))
        # Ensure target is within root using commonpath
        try:
            if os.path.commonpath([root, target]) != root:
                return None
        except ValueError:
            # Different drives on Windows
            return None

        # Resolve symlinks and check canonical destination
        real_target = os.path.realpath(target)
        try:
            if os.path.commonpath([root, real_target]) != root:
                return None
        except ValueError:
            return None
            
        return real_target

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        if action in ["file_read", "read"]:
            file_path = params.get("path")
            if not file_path:
                return ToolResult(status="error", error="Missing 'path' parameter.", side_effect_state="FAILED_NO_EFFECT")
                
            secure_path = self._secure_resolve_path(file_path)
            if not secure_path:
                return ToolResult(status="error", error="Path traversal attempt or invalid absolute path.", side_effect_state="FAILED_NO_EFFECT")
                
            if not os.path.exists(secure_path):
                return ToolResult(status="error", error=f"File not found: {file_path}", side_effect_state="FAILED_NO_EFFECT")
                
            if not os.path.isfile(secure_path):
                return ToolResult(status="error", error=f"Path is not a file: {file_path}", side_effect_state="FAILED_NO_EFFECT")
                
            file_size = os.path.getsize(secure_path)
            if file_size > 10 * 1024 * 1024:
                return ToolResult(status="error", error=f"File too large to read ({file_size} bytes).", side_effect_state="FAILED_NO_EFFECT")

            try:
                async with aiofiles.open(secure_path, 'r', encoding='utf-8') as f:
                    content = await f.read(MAX_CONTENT_CHARS + 1)
                    
                truncated = False
                if len(content) > MAX_CONTENT_CHARS:
                    content = content[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                    truncated = True
                    
                return ToolResult(
                    status="success",
                    data={
                        "path": file_path,
                        "content": content,
                        "truncated": truncated
                    },
                    side_effect_state="CONFIRMED"
                )
            except UnicodeDecodeError:
                return ToolResult(status="error", error="File is binary or not UTF-8 encoded.", side_effect_state="FAILED_NO_EFFECT")
            except Exception as e:
                return ToolResult(status="error", error=f"Failed to read file: {str(e)}", side_effect_state="FAILED_NO_EFFECT")
                
        return ToolResult(status="error", error=f"Unsupported action '{action}' for Filesystem.", side_effect_state="FAILED_NO_EFFECT")

    async def health_check(self, credentials: Any = None) -> Tuple[bool, Optional[str]]:
        root = self._get_workspace_root()
        if os.path.exists(root) and os.path.isdir(root):
            return True, f"Filesystem ready at {root}"
        return False, "Workspace root directory does not exist or is not a directory."

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        err = result.get("error") if hasattr(result, "get") else None
        if err or (hasattr(result, "status") and result.status == "error"):
            return VerificationOutcome(
                result="failed",
                evidence={"error": err or getattr(result, "error", "Unknown error")},
                reason=err or "Execution failed"
            )
        return VerificationOutcome(
            result="passed",
            evidence={"status": "verified"},
            reason="File read successfully"
        )
