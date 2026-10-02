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
# Maximum file size that may be written (1 MB)
MAX_WRITE_BYTES = 1 * 1024 * 1024


class LocalFilesystemTool(BaseTool):
    tool_type: str = "local"
    id: str = "local_filesystem"
    name: str = "Local Filesystem"
    description: str = "Read and write files within the configured local workspace sandbox."
    provides: List[str] = ["file_read", "file_write"]
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
            ),
            ActionSpec(
                action="file_write",
                capability_id="file_write",
                effect_class=EffectClass.NON_IDEMPOTENT_WRITE,
                reversible=False,
                target_param="path",
                required_permission=None,
                param_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path inside workspace to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "UTF-8 text content to write into the file"
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "If false (default), raise an error when the file already exists",
                            "default": False,
                        },
                    },
                    "required": ["path", "content"]
                },
                supports_idempotency_key=False
            ),
        ]

    def _get_workspace_root(self) -> str:
        base_dir = os.environ.get("RELAY_WORKSPACE_ROOT")
        if not base_dir:
            base_dir = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)
        return os.path.abspath(base_dir)

    def _secure_resolve_path(self, file_path: str) -> Optional[str]:
        """
        Resolves a relative path to an absolute path that is guaranteed to be
        inside the workspace sandbox.  Returns None if the path is rejected.

        Security checks (unchanged from original):
        - Absolute paths are rejected.
        - Paths that escape the workspace via .. are rejected.
        - Symlinks that point outside the workspace are rejected.
        - Works correctly on Windows (different-drive ValueError).
        """
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
        # ── file_read ────────────────────────────────────────────────────────
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

        # ── file_write ───────────────────────────────────────────────────────
        if action in ["file_write", "write"]:
            file_path = params.get("path")
            content = params.get("content")
            overwrite = bool(params.get("overwrite", False))

            if not file_path:
                return ToolResult(status="error", error="Missing 'path' parameter.", side_effect_state="FAILED_NO_EFFECT")
            if content is None:
                return ToolResult(status="error", error="Missing 'content' parameter.", side_effect_state="FAILED_NO_EFFECT")
            if not isinstance(content, str):
                return ToolResult(status="error", error="'content' must be a UTF-8 string.", side_effect_state="FAILED_NO_EFFECT")
            if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
                return ToolResult(
                    status="error",
                    error=f"Content exceeds maximum write size of {MAX_WRITE_BYTES} bytes.",
                    side_effect_state="FAILED_NO_EFFECT",
                )

            secure_path = self._secure_resolve_path(file_path)
            if not secure_path:
                return ToolResult(status="error", error="Path traversal attempt or invalid absolute path.", side_effect_state="FAILED_NO_EFFECT")

            if os.path.exists(secure_path) and not overwrite:
                return ToolResult(
                    status="error",
                    error=f"File already exists: {file_path}. Set overwrite=true to replace it.",
                    side_effect_state="FAILED_NO_EFFECT",
                )

            # Create parent directories inside sandbox if needed
            parent_dir = os.path.dirname(secure_path)
            root = os.path.realpath(self._get_workspace_root())
            try:
                if os.path.commonpath([root, os.path.realpath(os.path.abspath(parent_dir))]) != root:
                    return ToolResult(status="error", error="Parent directory is outside workspace sandbox.", side_effect_state="FAILED_NO_EFFECT")
            except ValueError:
                return ToolResult(status="error", error="Parent directory is outside workspace sandbox.", side_effect_state="FAILED_NO_EFFECT")

            try:
                os.makedirs(parent_dir, exist_ok=True)
                async with aiofiles.open(secure_path, 'w', encoding='utf-8') as f:
                    await f.write(content)

                bytes_written = len(content.encode("utf-8"))
                return ToolResult(
                    status="success",
                    data={
                        "path": file_path,
                        "bytes_written": bytes_written,
                        "overwrite": overwrite,
                    },
                    side_effect_state="CONFIRMED"
                )
            except Exception as e:
                return ToolResult(status="error", error=f"Failed to write file: {str(e)}", side_effect_state="UNCERTAIN")

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

        if action in ("file_write", "write"):
            # Independent read-back verification: confirm the written content is persisted
            file_path = params.get("path")
            expected_content = params.get("content", "")
            secure_path = self._secure_resolve_path(file_path) if file_path else None
            if secure_path and os.path.isfile(secure_path):
                try:
                    with open(secure_path, "r", encoding="utf-8") as fh:
                        actual = fh.read(MAX_CONTENT_CHARS)
                    # Verify at least the first MAX_CONTENT_CHARS match
                    if actual == expected_content[:MAX_CONTENT_CHARS]:
                        return VerificationOutcome(
                            result="passed",
                            evidence={"path": file_path, "bytes_written": result.get("bytes_written", 0)},
                            reason="File write independently verified by read-back"
                        )
                    return VerificationOutcome(
                        result="failed",
                        evidence={"path": file_path, "mismatch": True},
                        reason="Written content does not match expected content on read-back"
                    )
                except Exception as e:
                    return VerificationOutcome(
                        result="failed",
                        evidence={"path": file_path, "error": str(e)},
                        reason=f"Read-back verification failed: {e}"
                    )
            return VerificationOutcome(
                result="failed",
                evidence={"path": file_path},
                reason="File does not exist after write — write may have silently failed"
            )

        return VerificationOutcome(
            result="passed",
            evidence={"status": "verified"},
            reason="File read successfully"
        )

