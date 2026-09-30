import glob

def fix_file(fpath):
    with open(fpath, 'r') as f:
        content = f.read()
        
    content = content.replace('from app.tools.registry.base import BaseToolAdapter', 'from app.tools.registry.base import BaseTool')
    content = content.replace('class GitHubTool(BaseToolAdapter):', 'class GitHubTool(BaseTool):\n    tool_type: str = "api"')
    content = content.replace('class SlackTool(BaseToolAdapter):', 'class SlackTool(BaseTool):\n    tool_type: str = "api"')
    content = content.replace('class LocalFilesystemTool(BaseToolAdapter):', 'class LocalFilesystemTool(BaseTool):\n    tool_type: str = "local"')
    content = content.replace('class RestApiTool(BaseToolAdapter):', 'class RestApiTool(BaseTool):\n    tool_type: str = "api"')
    
    if 'async def verify(' not in content:
        content += '''
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
'''
    with open(fpath, 'w') as f:
        f.write(content)

for p in glob.glob('app/tools/adapters/*.py'):
    if p.endswith('github.py') or p.endswith('slack.py') or p.endswith('filesystem.py') or p.endswith('rest.py'):
        fix_file(p)
print('Fixed imports and base classes')
