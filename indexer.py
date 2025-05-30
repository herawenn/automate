import os, logging
from typing import Dict, List, Any, Set, Optional
from os.path import join, isfile, isdir, relpath, abspath, basename, getsize

logger = logging.getLogger(__name__)

DEFAULT_INDEXER_IGNORE_PATTERNS: Set[str] = {
    '.git', '__pycache__', 'node_modules', '.vscode', '.idea', 'build', 'dist',
    '.DS_Store', '*.pyc', '*.swp', '*.swo', '*.log', '*.tmp',
    'venv', '.venv', 'env', '.env', 'ENV',
    '*~', '*.bak', '*.tmp',
    '*.o', '*.obj', '*.dll', '*.so', '*.dylib',
}

class ProjectIndexer:
    def __init__(self, base_path: str, ignore_patterns: Optional[Set[str]] = None):
        self.base_path: str = abspath(base_path)
        self.ignore_patterns: Set[str] = ignore_patterns if ignore_patterns is not None else DEFAULT_INDEXER_IGNORE_PATTERNS
        self.file_index: Dict[str, Dict[str, Any]] = {}
        self.project_tree_str: str = "[Project tree not yet generated]"
        if not isdir(self.base_path):
            logger.warning(f"ProjectIndexer base path is not a directory: {self.base_path}. Index will be empty. Creating directory now.")
            try:
                os.makedirs(self.base_path, exist_ok=True)
                logger.info(f"Created base_path directory: {self.base_path}")
            except OSError as e:
                logger.error(f"Failed to create base_path directory {self.base_path}: {e}", exc_info=True)

    def _should_ignore(self, name: str, full_path: str) -> bool:
        if name in self.ignore_patterns:
            return True
        if name.startswith('.') and name not in {'.env'}:
            return True
        for pattern in self.ignore_patterns:
            if pattern.startswith('*') and name.endswith(pattern[1:]):
                return True
            if pattern.endswith('*') and name.startswith(pattern[:-1]):
                return True
        return False

    def refresh_index(self) -> None:
        logger.info(f"Starting full scan of project: {self.base_path}")
        new_file_index: Dict[str, Dict[str, Any]] = {}
        tree_lines: List[str] = [basename(self.base_path) + "/"]
        if not isdir(self.base_path):
            logger.error(f"Base path {self.base_path} is not a directory. Cannot scan.")
            self.project_tree_str = "[Error: Base project path not found or not a directory]"
            self.file_index = {}
            return
        try:
            for dir_path_str, dir_names_list, file_names_list in os.walk(self.base_path, topdown=True, onerror=None):
                dir_names_list[:] = [d for d in dir_names_list if not self._should_ignore(d, join(dir_path_str, d))]
                current_relative_dir_path = relpath(dir_path_str, self.base_path)
                depth = 0 if current_relative_dir_path == '.' else current_relative_dir_path.count(os.sep) + 1
                indent = '  ' * depth
                for dir_name in sorted(dir_names_list):
                    tree_lines.append(f"{indent}{dir_name}/")
                for file_name in sorted(file_names_list):
                    file_absolute_path = join(dir_path_str, file_name)
                    if self._should_ignore(file_name, file_absolute_path) or not isfile(file_absolute_path):
                        continue
                    file_relative_path = relpath(file_absolute_path, self.base_path)
                    tree_lines.append(f"{indent}{file_name}")
                    try:
                        new_file_index[file_relative_path.replace('\\', '/')] = {
                            "abs_path": file_absolute_path,
                            "size_bytes": getsize(file_absolute_path),
                        }
                    except OSError as e_file_stat:
                        logger.warning(f"Could not stat file {file_absolute_path} during indexing: {e_file_stat}")
                    except Exception as e_file_proc:
                        logger.warning(f"Error processing file {file_absolute_path} during indexing: {e_file_proc}", exc_info=True)
            self.file_index = new_file_index
            self.project_tree_str = "\n".join(tree_lines)
            logger.info(f"Project scan complete. Indexed {len(self.file_index)} files. Tree generated.")
        except Exception as e_walk:
            logger.error(f"Error during project walk for indexing ({self.base_path}): {e_walk}", exc_info=True)
            self.project_tree_str = "[Error generating project tree during scan]"
            self.file_index = {}

    def get_file_content(self, relative_path_key: str, max_size_bytes: int = 2 * 1024 * 1024) -> Optional[str]:
        normalized_rel_path = relative_path_key.replace('\\', '/')
        if normalized_rel_path not in self.file_index:
            logger.warning(f"Attempted to get content for non-indexed or missing file key: '{normalized_rel_path}'")
            return None
        file_info = self.file_index[normalized_rel_path]
        abs_path = file_info["abs_path"]
        try:
            if file_info["size_bytes"] == 0:
                return ""
            if file_info["size_bytes"] > max_size_bytes:
                logger.info(f"File {normalized_rel_path} ({file_info['size_bytes']} bytes) is too large to load full content (limit: {max_size_bytes} bytes).")
                return f"[Content of '{normalized_rel_path}' is too large to include fully ({file_info['size_bytes'] / (1024*1024):.2f}MB). Consider adding it to context with /add if essential.]"
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            logger.warning(f"File not found at {abs_path} though it was indexed. Consider re-indexing.")
            return f"[Error: File '{normalized_rel_path}' not found on disk. Please /reindex.]"
        except OSError as e_os:
            logger.error(f"OS error reading content of file {abs_path}: {e_os}", exc_info=True)
            return f"[OS Error reading content of '{normalized_rel_path}': {e_os.strerror}]"
        except Exception as e_generic:
            logger.error(f"Unexpected error reading content of file {abs_path}: {e_generic}", exc_info=True)
            return f"[Unexpected error reading content of '{normalized_rel_path}']"

    def get_project_tree(self) -> str:
        return self.project_tree_str

    def find_files_by_name_substring(self, substring: str, top_n: int = 10) -> List[Dict[str, Any]]:
        relevant_files: List[Dict[str, Any]] = []
        if not substring: return relevant_files
        substring_lower = substring.lower()
        count = 0
        for rel_path_key, file_data in self.file_index.items():
            if substring_lower in rel_path_key.lower():
                entry = {"relative_path": rel_path_key, **file_data}
                relevant_files.append(entry)
                count += 1
                if count >= top_n:
                    break
        logger.debug(f"Found {len(relevant_files)} files matching substring '{substring}'.")
        return relevant_files

    def get_all_indexed_files_info(self) -> List[Dict[str, Any]]:
        return [{"relative_path": k, **v} for k, v in self.file_index.items()]
