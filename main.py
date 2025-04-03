import os
import subprocess
from fastmcp import FastMCP, Response, Request
from fastmcp.resources import FileSystemResource, TerminalResource
from typing import Dict, Any, List

# Initialize the FastMCP server
app = FastMCP()

# Register resources
file_system = FileSystemResource()
terminal = TerminalResource()
app.register_resource(file_system)
app.register_resource(terminal)

@app.route("/github-push")
async def github_push(request: Request) -> Response:
    """
    Automate the process of pushing code to GitHub
    
    Expected request body:
    {
        "repo_url": "https://github.com/username/repo.git",
        "clone_directory": "/path/to/clone/directory", # Optional
        "commit_message": "Your commit message",
        "branch_name": "main", # Optional, defaults to main
        "specific_files": ["file1.py", "file2.js"] # Optional, pushes all files if not specified
    }
    """
    try:
        # Extract parameters from request
        data = request.json
        repo_url = data.get("repo_url")
        clone_directory = data.get("clone_directory", os.getcwd())
        commit_message = data.get("commit_message", "Automated commit via MCP agent")
        branch_name = data.get("branch_name", "main")
        specific_files = data.get("specific_files", None)
        
        # Step 1: Check if Git is installed and configured
        git_config = await check_git_config()
        if not git_config["is_configured"]:
            return Response(
                status=400,
                body={
                    "success": False,
                    "message": "Git is not properly configured. Please configure Git first.",
                    "details": git_config
                }
            )
        
        # Step 2: Clone the repository if repo_url is provided
        repo_name = repo_url.split("/")[-1].replace(".git", "") if repo_url else None
        repo_path = os.path.join(clone_directory, repo_name) if repo_name else clone_directory
        
        if repo_url:
            clone_result = await clone_repository(repo_url, clone_directory)
            if not clone_result["success"]:
                return Response(
                    status=400,
                    body={
                        "success": False,
                        "message": "Failed to clone repository",
                        "details": clone_result
                    }
                )
            repo_path = clone_result["repo_path"]
        
        # Step 3: Stage changes
        stage_result = await stage_changes(repo_path, specific_files)
        if not stage_result["success"]:
            return Response(
                status=400,
                body={
                    "success": False,
                    "message": "Failed to stage changes",
                    "details": stage_result
                }
            )
        
        # Step 4: Commit changes
        commit_result = await commit_changes(repo_path, commit_message)
        if not commit_result["success"]:
            return Response(
                status=400,
                body={
                    "success": False,
                    "message": "Failed to commit changes",
                    "details": commit_result
                }
            )
        
        # Step 5: Push changes
        push_result = await push_changes(repo_path, branch_name)
        if not push_result["success"]:
            return Response(
                status=400,
                body={
                    "success": False,
                    "message": "Failed to push changes",
                    "details": push_result
                }
            )
        
        return Response(
            status=200,
            body={
                "success": True,
                "message": f"Successfully pushed changes to {repo_url or 'repository'} on branch {branch_name}",
                "details": {
                    "git_config": git_config,
                    "clone": clone_result if repo_url else "Skipped",
                    "stage": stage_result,
                    "commit": commit_result,
                    "push": push_result
                }
            }
        )
    
    except Exception as e:
        return Response(
            status=500,
            body={
                "success": False,
                "message": f"An error occurred: {str(e)}",
                "error": str(e)
            }
        )

async def check_git_config() -> Dict[str, Any]:
    """Check if Git is installed and configured"""
    try:
        # Check if Git is installed
        result = await terminal.execute("git --version")
        if result.returncode != 0:
            return {
                "is_configured": False,
                "git_installed": False,
                "error": "Git is not installed"
            }
        
        # Check Git username
        username_result = await terminal.execute("git config user.name")
        username = username_result.stdout.strip() if username_result.returncode == 0 else None
        
        # Check Git email
        email_result = await terminal.execute("git config user.email")
        email = email_result.stdout.strip() if email_result.returncode == 0 else None
        
        return {
            "is_configured": bool(username and email),
            "git_installed": True,
            "username": username,
            "email": email
        }
    except Exception as e:
        return {
            "is_configured": False,
            "git_installed": False,
            "error": str(e)
        }

async def clone_repository(repo_url: str, directory: str) -> Dict[str, Any]:
    """Clone a GitHub repository"""
    try:
        # Create directory if it doesn't exist
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        # Extract repo name from URL for path
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = os.path.join(directory, repo_name)
        
        # Check if repository already exists
        if os.path.exists(repo_path):
            # If it exists, just pull the latest changes
            os.chdir(repo_path)
            pull_result = await terminal.execute("git pull")
            return {
                "success": pull_result.returncode == 0,
                "action": "pulled",
                "repo_path": repo_path,
                "output": pull_result.stdout,
                "error": pull_result.stderr if pull_result.returncode != 0 else None
            }
        
        # Clone the repository
        os.chdir(directory)
        clone_result = await terminal.execute(f"git clone {repo_url}")
        
        return {
            "success": clone_result.returncode == 0,
            "action": "cloned",
            "repo_path": repo_path,
            "output": clone_result.stdout,
            "error": clone_result.stderr if clone_result.returncode != 0 else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def stage_changes(repo_path: str, specific_files: List[str] = None) -> Dict[str, Any]:
    """Stage changes in a repository"""
    try:
        os.chdir(repo_path)
        
        # Check status before staging
        status_before = await terminal.execute("git status")
        
        # Stage specific files or all changes
        if specific_files:
            results = []
            for file in specific_files:
                result = await terminal.execute(f"git add {file}")
                results.append({
                    "file": file,
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.returncode != 0 else None
                })
            
            success = all(r["success"] for r in results)
            return {
                "success": success,
                "action": "staged_specific_files",
                "files": specific_files,
                "results": results
            }
        else:
            # Stage all changes
            result = await terminal.execute("git add .")
            return {
                "success": result.returncode == 0,
                "action": "staged_all",
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def commit_changes(repo_path: str, commit_message: str) -> Dict[str, Any]:
    """Commit staged changes"""
    try:
        os.chdir(repo_path)
        
        # Check if there are changes to commit
        status_result = await terminal.execute("git status")
        if "nothing to commit" in status_result.stdout:
            return {
                "success": True,
                "action": "no_changes",
                "message": "No changes to commit"
            }
        
        # Commit changes
        result = await terminal.execute(f'git commit -m "{commit_message}"')
        
        return {
            "success": result.returncode == 0,
            "action": "committed",
            "commit_message": commit_message,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

async def push_changes(repo_path: str, branch_name: str) -> Dict[str, Any]:
    """Push committed changes to remote repository"""
    try:
        os.chdir(repo_path)
        
        # Push changes
        result = await terminal.execute(f"git push origin {branch_name}")
        
        return {
            "success": result.returncode == 0,
            "action": "pushed",
            "branch": branch_name,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)