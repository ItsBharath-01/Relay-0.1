import os
import aiofiles
from typing import Dict, Any, List, Optional
from app.tools.registry.base import BaseTool

MAX_CONTENT_CHARS = 8000

class LocalFilesystemTool(BaseTool):
    tool_type: str = "local"
    id: str = "local_filesystem"
    name: str = "Local Filesystem"
    description: str = "Read files from the configured local workspace."
    provides: List[str] = ["file_read"]
    requires_connection: Optional[str] = None

    def _get_workspace_root(self) -> str:
        # Default to a specific workspace directory inside the project root for safety
        base_dir = os.environ.get("RELAY_WORKSPACE_ROOT")
        if not base_dir:
            base_dir = os.path.abspath(os.path.join(os.getcwd(), "workspace"))
            if not os.path.exists(base_dir):
                os.makedirs(base_dir, exist_ok=True)
        return os.path.abspath(base_dir)

    def _secure_resolve_path(self, file_path: str) -> Optional[str]:
        """Resolves a path securely ensuring it does not escape the workspace root."""
        root = self._get_workspace_root()
        
        # Don't allow absolute paths from root if they don't start with workspace root
        if os.path.isabs(file_path):
            return None
            
        resolved = os.path.abspath(os.path.join(root, file_path))
        
        # Check for path traversal escape
        if not resolved.startswith(root):
            return None
            
        return resolved

    async def execute(self, capability: str, params: Dict[str, Any], credentials: Any = None) -> Dict[str, Any]:
        if capability == "file_read":
            file_path = params.get("path")
            if not file_path:
                return {"error": "Missing 'path' parameter."}
                
            secure_path = self._secure_resolve_path(file_path)
            if not secure_path:
                return {"error": "Path traversal attempt or invalid absolute path."}
                
            if not os.path.exists(secure_path):
                return {"error": f"File not found: {file_path}"}
                
            if not os.path.isfile(secure_path):
                return {"error": f"Path is not a file: {file_path}"}
                
            # Enforce size limits before reading completely
            file_size = os.path.getsize(secure_path)
            if file_size > 10 * 1024 * 1024:  # 10MB hard limit for safety
                return {"error": f"File too large to read ({file_size} bytes)."}

            try:
                async with aiofiles.open(secure_path, 'r', encoding='utf-8') as f:
                    content = await f.read(MAX_CONTENT_CHARS + 1)
                    
                truncated = False
                if len(content) > MAX_CONTENT_CHARS:
                    content = content[:MAX_CONTENT_CHARS] + "\n... [TRUNCATED]"
                    truncated = True
                    
                return {
                    "path": file_path,
                    "content": content,
                    "truncated": truncated
                }
            except UnicodeDecodeError:
                return {"error": "File is binary or not UTF-8 encoded."}
            except Exception as e:
                return {"error": f"Failed to read file: {str(e)}"}
                
        return {"error": f"Unsupported capability '{capability}' for Filesystem."}

    async def health_check(self, credentials: Any = None) -> tuple[bool, str]:
        root = self._get_workspace_root()
        if os.path.exists(root) and os.path.isdir(root):
            return True, f"Filesystem ready at {root}"
        return False, "Workspace root directory does not exist or is not a directory."

    async def verify(
        self,
        action: str,
        params: dict,
        result: dict,
        credentials=None
    ) -> tuple[bool, dict]:
        if "error" in result:
            return False, {"error": result["error"]}
        return True, {"status": "verified"}
