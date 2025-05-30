import os, re, sys, stream, helper, database, keyboard
import asyncio, textwrap, threading, subprocess, logging, difflib
from os.path import (abspath, basename, dirname, exists, getsize, isfile, join, relpath, isdir)
from typing import Any, Dict, List, Optional, Set, Tuple
from colorama import Fore, Style
from indexer import ProjectIndexer, DEFAULT_INDEXER_IGNORE_PATTERNS
from voice import VoiceCommandHandler

logger = logging.getLogger(__name__)

CHECKMARK = '✓'
X_MARK = '✗'
MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT = 10000
MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT = 50000
MAX_CHARS_FOR_SUMMARIZATION_INPUT = 15000
MIN_CHARS_TO_TRIGGER_SUMMARIZATION = MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT * 1.5

class ChatBot:
    DEFAULT_IGNORE_DIRS: Set[str] = DEFAULT_INDEXER_IGNORE_PATTERNS
    USERNAME: str = "User"
    AGENT_NAME: str = "Agent"

    def __init__(self, db_conn: database.DbConnection, code_folder_path: str, default_admin_mode: Optional[str]):
        self.active_files_pinned: Set[str] = set()
        self.conn: database.DbConnection = db_conn
        self.settings: Optional[Dict[str, Any]] = database.load_settings(self.conn, default_admin_mode)
        self.last_proposed_changes: Optional[Dict[str, Dict[str, Any]]] = None
        self._voice_processing_thread: Optional[threading.Thread] = None
        self.voice_handler: Optional[VoiceCommandHandler] = None
        self.hotkeys_active: bool = False

        if not self.settings:
             logger.critical("Failed to load settings from database. Cannot proceed.")
             print(f"{Fore.RED}{Style.BRIGHT}Fatal Error: Could not load settings from database. Check logs.{Style.RESET_ALL}")
             raise RuntimeError("Failed to load essential settings from database.")

        self.code_folder_path: str = abspath(code_folder_path)
        logger.info(f"ChatBot using Code Folder: {self.code_folder_path}")

        self.project_indexer = ProjectIndexer(self.code_folder_path, ignore_patterns=self.DEFAULT_IGNORE_DIRS)
        try:
            self.project_indexer.refresh_index()
        except Exception as e_scan:
            logger.error(f"Initial project scan failed for {self.code_folder_path}: {e_scan}", exc_info=True)
            print(f"{Fore.RED}{Style.BRIGHT}Warning: Failed to fully index project at {self.code_folder_path}. Context may be limited.{Style.RESET_ALL}")

        self.command_list: Dict[str, str] = {
            "/help": "Show this help message.",
            "/quit": "Exit the application.",
            "/exit": "Exit the application.",
            "/clear": "Clear the terminal screen.",
            "/add": "Pin file(s) or all files in a directory to the immediate context. Usage: /add <path_in_project>...",
            "/drop": "Unpin file(s) or 'all' from the immediate context. Usage: /drop <filename_or_path_or_all>...",
            "/list": "List pinned files and show project index summary.",
            "/apply": "Review & apply proposed code changes (auto-executes Python files if Admin ON).",
            "/discard": "Discard proposed code changes.",
            "/model": "View/change AI model client. Usage: /model [client_name]",
            "/settings": "Display or modify application settings. Usage: /settings [key value]",
            "/codefolder": "Show the configured Code Folder path.",
            "/sudo": "Toggle Admin Mode (allows file creation/execution). Usage: /sudo [on|off]",
            "/runtest": "Run the configured test command. Usage: /runtest [optional_args]",
            "/reindex": "Manually rescan the Code Folder and refresh the project index.",
            "/find": "Search for files in the project index by name. Usage: /find <substring>"
        }
        if stream:
            self.command_list["/capture_context"] = "Capture screen & send with prompt to AI. Usage: /capture_context [prompt]"

        if keyboard:
            self._setup_voice_input()
            self._setup_keyboard_shortcuts()

        logger.info(f"ChatBot initialized. Project indexed at: {self.code_folder_path}")

    def _display_system_message(self, message: str) -> None:
        try:
            print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"Error displaying system message ('{message}'): {e}", exc_info=True)
            print(f"System: {message}")

    def _display_error(self, message: str) -> None:
        try:
            print(f"{Fore.RED}{Style.BRIGHT}Error: {message}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"Error displaying error message itself ('{message}'): {e}", exc_info=True)
            print(f"Error: {message}")

    def _display_agent_message(self, message: str) -> None:
        try:
            print(f"{Fore.CYAN}{self.AGENT_NAME}{Style.RESET_ALL}:\n{textwrap.indent(message, '  ')}")
        except Exception as e:
            logger.error(f"Error displaying agent message: {e}", exc_info=True)
            print(f"{self.AGENT_NAME}:\n{message}")

    def _display_prompt(self) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded. Prompt cannot be displayed.")
                return
            
            is_admin: bool = bool(self.settings.get('admin_mode_enabled', False))
            
            if is_admin:
                admin_indicator = f"{Fore.GREEN}{Style.BRIGHT}{CHECKMARK}{Style.RESET_ALL}"
            else:
                admin_indicator = f"{Fore.RED}{X_MARK}{Style.RESET_ALL}"
                
            prompt_string: str = f"\n({admin_indicator}) {Fore.YELLOW}{self.USERNAME}{Style.RESET_ALL}: "
            print(prompt_string, end="")
            
        except Exception as e:
            logger.error(f"Error displaying prompt: {e}", exc_info=True)
            print(f"\nError displaying prompt. Check logs. {self.USERNAME}: ", end="")

    def _summarize_content_if_needed(self, file_rel_path: str, full_content: str) -> Tuple[str, bool]:
        if len(full_content) > MIN_CHARS_TO_TRIGGER_SUMMARIZATION and self.settings:
            self._display_system_message(f"Content of '{file_rel_path}' ({len(full_content)} chars) is large. Attempting summarization...")
            summarization_prompt = (
                f"Summarize the following content from the file '{file_rel_path}'. "
                f"Focus on the core logic, main functionalities, and purpose of the code or text. "
                f"The summary should be concise and capture the essence of the file for an AI assistant to understand its role in a larger project. "
                f"Keep the summary under {MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT // 2} characters if possible.\n\n"
                f"Full content of '{file_rel_path}':\n```\n{full_content[MAX_CHARS_FOR_SUMMARIZATION_INPUT]}\n```"
            )
            if len(full_content) > MAX_CHARS_FOR_SUMMARIZATION_INPUT:
                summarization_prompt += "\n(Note: Original content was truncated for this summarization prompt)"

            summarization_model_client = self.settings.get('model_name', 'gemini')
            if summarization_model_client not in helper.SUPPORTED_MODELS or not helper.SUPPORTED_MODELS[summarization_model_client].get("client"):
                available_models = [name for name, cfg in helper.SUPPORTED_MODELS.items() if cfg.get("client")]
                if available_models:
                    summarization_model_client = available_models[0]
                    logger.warning(f"Summarization model '{self.settings.get('model_name')}' unavailable, using '{summarization_model_client}' for summarization.")
                else:
                    logger.error("No models available for summarization. Returning truncated content.")
                    self._display_error("Failed to summarize: No AI models available.")
                    return full_content[:MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT], False

            summary = helper.chat_with_model([summarization_prompt], model_name=summarization_model_client, mode_hint='conversation')

            if summary and not summary.startswith("Error:"):
                self._display_system_message(f"Summarized '{file_rel_path}'. Original: {len(full_content)} chars, Summary: {len(summary)} chars.")
                logger.info(f"Content for {file_rel_path} summarized. Original length: {len(full_content)}, Summary length: {len(summary)}")
                return f"[Summarized Content of {file_rel_path}]:\n{summary}", True
            else:
                self._display_error(f"Failed to summarize '{file_rel_path}'. Using truncated content. AI Error: {summary}")
                logger.warning(f"Summarization failed for {file_rel_path}. Fallback to truncation. Error: {summary}")
                return full_content[:MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT], False
        elif len(full_content) > MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT:
            return full_content[:MAX_INDEXED_FILE_CONTENT_CHARS_IN_PROMPT], False
        return full_content, False

    def _build_prompt_with_context(self, user_message: str) -> List[helper.GoogleGenAIContentType]:
        content_parts: List[helper.GoogleGenAIContentType] = []
        total_chars_from_files = 0
        try:
            if not self.settings:
                logger.error("Settings not available in _build_prompt_with_context.")
                return [f"{Fore.RED}Error: Application settings are missing.{Style.RESET_ALL}"]

            admin_status_text: str = 'ENABLED (AI can propose file system changes and run commands if confirmed by user)' if self.settings.get('admin_mode_enabled', False) else 'DISABLED (AI file system changes and command execution are off)'
            system_prompt_header_text: str = textwrap.dedent(f"""
                You are an AI assistant specialized in code generation, analysis, and modification for the project located at '{self.code_folder_path}'.
                Admin Mode: {admin_status_text}.
                When proposing changes to existing files or suggesting new files, use the following format precisely for each file:
                # FILEPATH: path/relative/to/project_root/filename.ext
                ```optional_language_marker
                (full content of the file or code block)
                ```
                Ensure filepaths are relative to the project root: '{basename(self.code_folder_path)}/'.
            """).strip()
            content_parts.append(system_prompt_header_text)

            project_tree_str = self.project_indexer.get_project_tree()
            system_prompt_context_text: str = f"\n\n--- Project Codebase Structure ({basename(self.code_folder_path)}/) ---\n{project_tree_str}\n--- End Project Codebase Structure ---"
            content_parts.append(system_prompt_context_text)

            files_for_context_content: Dict[str, str] = {}
            files_for_context_log: List[str] = []

            temp_unpinnable_files = set()
            for pinned_abs_path in self.active_files_pinned:
                try:
                    pinned_rel_path = relpath(pinned_abs_path, self.project_indexer.base_path).replace('\\', '/')
                    if pinned_rel_path not in self.project_indexer.file_index:
                        self._display_error(f"Pinned file '{basename(pinned_abs_path)}' no longer in index. Unpinning.")
                        logger.warning(f"Pinned file {pinned_abs_path} not in index. Marking for unpin.")
                        temp_unpinnable_files.add(pinned_abs_path)
                        continue

                    current_file_original_content = self.project_indexer.get_file_content(pinned_rel_path)
                    if not current_file_original_content:
                        files_for_context_log.append(f"{pinned_rel_path} (pinned, 0 chars or error reading)")
                        if current_file_original_content is not None :
                             files_for_context_content[pinned_rel_path] = ""
                        continue

                    content_to_add, was_summarized = self._summarize_content_if_needed(pinned_rel_path, current_file_original_content)

                    if total_chars_from_files + len(content_to_add) > MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT:
                        chars_can_add = MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT - total_chars_from_files
                        if chars_can_add <=0:
                            logger.warning(f"Max total file content limit ({MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT} chars) reached. Cannot add more file content including '{pinned_rel_path}'.")
                            self._display_system_message(f"Warning: Max total file content limit reached. Cannot include content from '{basename(pinned_abs_path)}' or subsequent files.")
                            break
                        content_to_add = content_to_add[:chars_can_add]
                        log_suffix = " - heavily truncated due to total limit"

                    else:
                        log_suffix = " - summarized" if was_summarized else (" - truncated" if len(content_to_add) < len(current_file_original_content) else "")

                    files_for_context_content[pinned_rel_path] = content_to_add
                    files_for_context_log.append(f"{pinned_rel_path} (pinned, {len(content_to_add)} chars){log_suffix}")
                    total_chars_from_files += len(content_to_add)

                    if total_chars_from_files >= MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT:
                        logger.info(f"Max total file content limit ({MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT} chars) reached after adding '{pinned_rel_path}'.")
                        self._display_system_message(f"Warning: Max total file content limit reached. Further pinned files may be skipped or truncated.")
                        break

                except Exception as e_pin_file:
                    logger.error(f"Error processing pinned file {pinned_abs_path}: {e_pin_file}", exc_info=True)
                    self._display_error(f"Error accessing pinned file '{basename(pinned_abs_path)}'.")
            for unpin_path in temp_unpinnable_files: self.active_files_pinned.discard(unpin_path)

            context_blocks_text_list: List[str] = []
            if not files_for_context_content:
                context_blocks_text_list.append("\nNo specific file contents are currently pinned. Use '/add <path>' to pin files for focus.")
            else:
                context_blocks_text_list.append(f"\n\nThe following file contents are provided ({len(files_for_context_content)} files, total {total_chars_from_files} chars):")
                for rel_path_key, content_str in files_for_context_content.items():
                    context_blocks_text_list.append(f"\n`{rel_path_key}`\n```\n{content_str}\n```")

            content_parts.append("\n".join(context_blocks_text_list))
            content_parts.append(f"\n\n---\n\nUser request:\n{user_message}")
            logger.info(f"Built prompt. Included content from files: {files_for_context_log if files_for_context_log else 'None'}")
            return content_parts
        except Exception as e:
            logger.error(f"Error building prompt with context: {e}", exc_info=True)
            return [f"{Fore.RED}Internal Error: Could not build the full prompt context. {e}{Style.RESET_ALL}"]

    def _parse_llm_response_for_changes(self, response_text: str) -> Optional[Dict[str, Dict[str, Any]]]:
        try:
            regex = r"#\s*FILEPATH\s*:\s*([^\n`]+?)\s*\n(?:```(?:[\w.-]+)?\n)?(.*?)(?:\n```|\Z)"
            matches = re.finditer(regex, response_text, re.DOTALL | re.MULTILINE)

            proposed_changes: Dict[str, Dict[str, Any]] = {}
            found_change: bool = False
            code_folder_abs: str = self.project_indexer.base_path

            for match_num, match in enumerate(matches):
                original_identifier: str = match.group(1).strip().replace('\\', '/')
                new_content: str = match.group(2)

                original_identifier = original_identifier.strip('\'"` ')
                if not original_identifier:
                    logger.warning(f"Empty filepath identifier found in LLM response at match {match_num}. Skipping.")
                    continue

                if new_content.endswith("\n```"):
                    new_content = new_content[:-4]
                elif new_content.endswith("```"):
                     new_content = new_content[:-3]
                new_content_normalized = new_content.strip()

                temp_target_path: str

                if os.path.isabs(original_identifier):
                    if not original_identifier.startswith(code_folder_abs):
                        logger.warning(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): LLM proposed absolute path '{original_identifier}' outside project. Attempting to make relative.")
                        project_base_name = basename(code_folder_abs)
                        try:
                            if project_base_name + os.sep in original_identifier:
                                rel_part = original_identifier.split(project_base_name + os.sep, 1)[1]
                                temp_target_path = abspath(join(code_folder_abs, rel_part))
                                logger.info(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Interpreted as relative: '{rel_part}' -> '{temp_target_path}'")
                            else:
                                logger.warning(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Could not reliably make '{original_identifier}' relative using project name. Using its basename: '{basename(original_identifier)}'.")
                                temp_target_path = abspath(join(code_folder_abs, basename(original_identifier)))
                        except IndexError:
                            logger.error(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Error making '{original_identifier}' relative. Using its basename.")
                            temp_target_path = abspath(join(code_folder_abs, basename(original_identifier)))
                    else:
                        temp_target_path = abspath(original_identifier)
                        logger.info(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Is absolute and inside project: '{temp_target_path}'")
                else:
                    temp_target_path = abspath(join(code_folder_abs, original_identifier))
                    logger.info(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Is relative, resolved to: '{temp_target_path}'")

                if not temp_target_path.startswith(code_folder_abs):
                    logger.error(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Security Risk: Final resolved path '{temp_target_path}' is outside project folder '{code_folder_abs}'. Skipping this change.")
                    self._display_error(f"Skipped change for '{original_identifier}' - resolved path ('{temp_target_path}') is outside project boundaries.")
                    continue

                target_path_abs = temp_target_path
                is_new = not exists(target_path_abs)

                new_content_final = '\n'.join(new_content_normalized.splitlines())

                change_key = f"{original_identifier}_{match_num}"
                proposed_changes[change_key] = {
                    'original_identifier': original_identifier,
                    'target_path_abs': target_path_abs,
                    'content': new_content_final,
                    'is_new': is_new,
                }
                found_change = True
                logger.info(f"Change proposal {match_num} (LLM ID: '{original_identifier}'): Parsed for {'NEW' if is_new else 'EXISTING'} file. Resolved abs: '{target_path_abs}'. Content length: {len(new_content_final)}.")

            if found_change:
                self.last_proposed_changes = proposed_changes
                return proposed_changes
            else:
                logger.info("No parsable file changes found in LLM response using the defined format.")
                self.last_proposed_changes = None
                return None
        except Exception as e:
            logger.error(f"Error parsing LLM response for changes: {e}", exc_info=True)
            self._display_error("Error parsing code changes from AI's response.")
            self.last_proposed_changes = None
            return None

    def _display_diff(self, filepath_abs: str, new_content: str) -> bool:
        try:
            new_content_lines_for_diff: List[str] = [line + '\n' for line in new_content.splitlines()]
            if not new_content.strip() and not new_content_lines_for_diff:
                new_content_lines_for_diff = ['\n'] if new_content == "" else []

            with open(filepath_abs, 'r', encoding='utf-8', errors='replace') as f:
                current_content_lines: List[str] = f.read().splitlines(keepends=True)

            try:
                relative_display_path: str = relpath(filepath_abs, start=self.project_indexer.base_path).replace('\\', '/')
            except ValueError:
                relative_display_path = basename(filepath_abs)

            diff = difflib.unified_diff(
                current_content_lines,
                new_content_lines_for_diff,
                fromfile=f"a/{relative_display_path}",
                tofile=f"b/{relative_display_path}",
                lineterm=''
            )

            diff_text: str = "".join(list(diff))
            if not diff_text.strip():
                current_content_normalized_for_compare = '\n'.join(''.join(current_content_lines).splitlines())
                if current_content_normalized_for_compare == new_content:
                    logger.info(f"No functional changes (content identical after normalization) for {relative_display_path}.")
                    return False

            print(f"{Fore.BLUE}Diff for {relative_display_path}{Style.RESET_ALL}")
            for line in diff_text.splitlines():
                if line.startswith('+') and not line.startswith('+++'):
                    print(f"{Fore.GREEN}{line}{Style.RESET_ALL}")
                elif line.startswith('-') and not line.startswith('---'):
                    print(f"{Fore.RED}{line}{Style.RESET_ALL}")
                elif line.startswith('@@'):
                    print(f"{Fore.CYAN}{line}{Style.RESET_ALL}")
                else:
                    print(line)
            return True
        except FileNotFoundError:
            self._display_error(f"Cannot display diff: Original file {basename(filepath_abs)} not found at {filepath_abs}.")
            logger.warning(f"Original file not found for diff: {filepath_abs}")
            return False
        except Exception as e:
            self._display_error(f"Error generating/displaying diff for {basename(filepath_abs)}: {e}")
            logger.error(f"Error generating/displaying diff for {filepath_abs}: {e}", exc_info=True)
            return False

    def _review_and_apply_changes(self, args: Optional[List[str]] = None) -> None:
        try:
            if not self.last_proposed_changes:
                self._display_system_message("No changes available to apply.")
                return

            applied_files_abs_paths: List[str] = []
            skipped_confirm_create_files: List[str] = []
            skipped_file_abs_paths: List[str] = []
            changes_to_apply_confirmed: Dict[str, Dict[str, Any]] = {}

            self._display_system_message("\n--- Review Proposed Code Changes ---")
            sorted_changes_items = sorted(self.last_proposed_changes.items(), key=lambda item: item[1]['target_path_abs'])

            goto_apply_all_flag = False
            goto_skip_all_flag = False
            admin_mode_on = bool(self.settings and self.settings.get('admin_mode_enabled', False))

            for change_key, change_info in sorted_changes_items:
                if goto_skip_all_flag:
                    skipped_file_abs_paths.append(change_info['target_path_abs'])
                    logger.info(f"Auto-skipping (due to 'skip all') change for {change_info['original_identifier']}")
                    continue

                target_path_abs: str = change_info['target_path_abs']
                new_content: str = change_info['content']
                is_new: bool = change_info['is_new']
                original_identifier: str = change_info['original_identifier']
                display_rel_path = relpath(target_path_abs, self.project_indexer.base_path).replace('\\','/')

                if is_new and admin_mode_on and not goto_apply_all_flag:
                    print("-" * 40)
                    self._display_system_message(f"AI proposes to CREATE a NEW file: {Fore.CYAN}{display_rel_path}{Style.RESET_ALL}")
                    self._display_system_message(f"(Original LLM identifier: '{original_identifier}')")
                    print(f"{Fore.GREEN}+ Proposed content snippet:{Style.RESET_ALL}")
                    display_limit_snippet: int = 300
                    print(textwrap.indent(new_content[:display_limit_snippet], '  '))
                    if len(new_content) > display_limit_snippet:
                        print(textwrap.indent(f"... (content truncated - {len(new_content)} chars total)", '  '))

                    confirm_create = input(f"Allow creation of this new file '{display_rel_path}'? (y/n/s) [y]: ").lower().strip()
                    if confirm_create == 'n':
                        self._display_system_message(f"Creation of new file '{display_rel_path}' DENIED by user.")
                        skipped_confirm_create_files.append(target_path_abs)
                        logger.info(f"User denied creation of new file: {target_path_abs}")
                        continue
                    elif confirm_create == 's':
                        self._display_system_message(f"Skipping creation of '{display_rel_path}' and all subsequent proposals as per user request.")
                        skipped_confirm_create_files.append(target_path_abs)
                        logger.info(f"User chose to skip this and all subsequent proposals, starting with new file: {target_path_abs}")
                        goto_skip_all_flag = True
                        continue
                    elif confirm_create not in ('y', ''):
                         self._display_error("Invalid input. Assuming 'yes' to review this new file for application.")

                any_diff_shown_or_new_content_displayed: bool = False
                print("-" * 40)

                if is_new:
                    print(f"{Fore.BLUE}Proposed NEW file: {display_rel_path} (from LLM id: '{original_identifier}'){Style.RESET_ALL}")
                    print(f"{Fore.GREEN}+ Proposed content:{Style.RESET_ALL}")
                    display_limit_full: int = 2000
                    print(textwrap.indent(new_content[:display_limit_full], '  '))
                    if len(new_content) > display_limit_full:
                        print(textwrap.indent(f"... (content truncated - {len(new_content)} chars total)", '  '))
                    any_diff_shown_or_new_content_displayed = True
                else:
                    print(f"{Fore.BLUE}Proposed changes for EXISTING file: {display_rel_path} (from LLM id: '{original_identifier}'){Style.RESET_ALL}")
                    if exists(target_path_abs):
                        if self._display_diff(target_path_abs, new_content):
                            any_diff_shown_or_new_content_displayed = True
                        else:
                            self._display_system_message(f"No textual changes for '{display_rel_path}' or content identical/error in diff. Check logs.")
                    else:
                        self._display_error(f"Original file '{display_rel_path}' not found (it may have been deleted or renamed). Treating this as a new file proposal.")
                        print(f"{Fore.GREEN}+ Proposed full content for {display_rel_path}:{Style.RESET_ALL}")
                        display_limit_full_alt: int = 1000
                        print(textwrap.indent(new_content[:display_limit_full_alt], '  '))
                        if len(new_content) > display_limit_full_alt:
                             print(textwrap.indent(f"... (content truncated - {len(new_content)} chars total)", '  '))
                        any_diff_shown_or_new_content_displayed = True
                        change_info['is_new'] = True

                if any_diff_shown_or_new_content_displayed or goto_apply_all_flag:
                    if goto_apply_all_flag:
                        changes_to_apply_confirmed[change_key] = change_info
                        self._display_system_message(f"Auto-confirming changes for '{display_rel_path}' due to 'apply all'.")
                    else:
                        print("-" * 40)
                        while True:
                            try:
                                confirm = input(f"Apply changes to '{display_rel_path}'? (y/n/d/a/s/?) [y]: ").lower().strip()
                                if confirm in ('y', ''):
                                    changes_to_apply_confirmed[change_key] = change_info
                                    break
                                elif confirm == 'n':
                                    skipped_file_abs_paths.append(target_path_abs)
                                    logger.info(f"User skipped applying changes to {target_path_abs}")
                                    break
                                elif confirm == 'd':
                                    print(f"{Fore.GREEN}+ Proposed full content for {display_rel_path}:{Style.RESET_ALL}\n{textwrap.indent(new_content, '  ')}\n")
                                elif confirm == 'a':
                                    changes_to_apply_confirmed[change_key] = change_info
                                    goto_apply_all_flag = True
                                    self._display_system_message("Marked this and all subsequent changes for application.")
                                    break
                                elif confirm == 's':
                                    skipped_file_abs_paths.append(target_path_abs)
                                    goto_skip_all_flag = True
                                    self._display_system_message("Marked this and all subsequent changes to be skipped.")
                                    break
                                elif confirm == '?':
                                    print(" y: yes (default)\n n: no\n d: display full proposed content for this file\n a: apply this change AND all subsequent changes automatically\n s: skip this change AND all subsequent changes automatically\n ?: this help message")
                                else:
                                    print("Invalid input. Please enter y, n, d, a, s, or ?.")
                            except EOFError:
                                self._display_error("\nConfirmation aborted by user (EOF). Skipping this change.")
                                skipped_file_abs_paths.append(target_path_abs)
                                break
                else:
                    self._display_system_message(f"Auto-skipping '{display_rel_path}' as no applicable changes were displayed or file was new without admin pre-confirmation step being met.")
                    skipped_file_abs_paths.append(target_path_abs)

            if not changes_to_apply_confirmed:
                self._display_system_message("No changes were confirmed for application.")
                if skipped_confirm_create_files:
                    skipped_rel_paths = [relpath(p, self.project_indexer.base_path).replace('\\','/') for p in skipped_confirm_create_files]
                    self._display_system_message(f"New file creations denied for: {', '.join(skipped_rel_paths)}")
                self.last_proposed_changes = None
                return

            self._display_system_message("\n--- Applying Confirmed Changes ---")
            needs_reindex = False

            for change_key, change_info in sorted(changes_to_apply_confirmed.items(), key=lambda item: item[1]['target_path_abs']):
                target_path_abs = change_info['target_path_abs']
                new_content = change_info['content']

                display_rel_path = relpath(target_path_abs, self.project_indexer.base_path).replace('\\','/')

                try:
                    target_dir: str = dirname(target_path_abs)
                    if target_dir:
                        os.makedirs(target_dir, exist_ok=True)

                    is_new_at_write_time = not exists(target_path_abs)

                    with open(target_path_abs, 'w', encoding='utf-8', newline='\n') as f:
                        f.write(new_content)

                    action: str = "Created" if is_new_at_write_time else "Modified"
                    self._display_system_message(f"{action} '{display_rel_path}'.")
                    applied_files_abs_paths.append(target_path_abs)
                    needs_reindex = True

                    if admin_mode_on and target_path_abs.lower().endswith(".py") and isfile(target_path_abs):
                        self._display_system_message(f"Admin Mode ON: Automatically attempting to execute {action.lower()} Python script: '{display_rel_path}'...")
                        self._execute_script_in_new_terminal(target_path_abs)

                    if target_path_abs not in self.active_files_pinned:
                        if isfile(target_path_abs):
                            self.active_files_pinned.add(target_path_abs)
                            logger.info(f"Auto-pinned {'new' if is_new_at_write_time else 'modified'} file: {display_rel_path}")
                            self._display_system_message(f"Note: '{display_rel_path}' is now pinned.")
                except OSError as e:
                    self._display_error(f"Failed to write file {display_rel_path}: {e.strerror}")
                    logger.error(f"OSError writing file {target_path_abs}: {e}", exc_info=True)
                    skipped_file_abs_paths.append(target_path_abs)
                except Exception as e:
                    self._display_error(f"Unexpected error writing file {display_rel_path}: {e}")
                    logger.error(f"Unexpected error writing file {target_path_abs}: {e}", exc_info=True)
                    skipped_file_abs_paths.append(target_path_abs)

            if applied_files_abs_paths:
                applied_rel_paths = sorted(list(set(relpath(p, self.project_indexer.base_path).replace('\\','/') for p in applied_files_abs_paths)))
                self._display_system_message(f"\nChanges applied successfully to: {', '.join(applied_rel_paths)}")

                if admin_mode_on and self.settings and self.settings.get('test_command'):
                    test_command: Optional[str] = self.settings.get('test_command')
                    if test_command:
                        self._display_system_message("Admin mode is ON and a global test command is configured. Running global tests...")
                        self._run_test_command_internal(test_command)

            all_skipped_abs = set(skipped_file_abs_paths) | set(skipped_confirm_create_files)
            unique_skipped_rel_paths = sorted(list(set(
                relpath(p, self.project_indexer.base_path).replace('\\','/')
                for p in all_skipped_abs
                if p not in applied_files_abs_paths
            )))
            if unique_skipped_rel_paths:
                self._display_system_message(f"Some changes were SKIPPED, DENIED, or FAILED for: {', '.join(unique_skipped_rel_paths)}")

            if needs_reindex:
                self._display_system_message("Re-indexing project due to file changes...")
                self.project_indexer.refresh_index()

            self.last_proposed_changes = None

        except Exception as e:
            logger.error(f"Critical error in _review_and_apply_changes: {e}", exc_info=True)
            self._display_error(f"A critical error occurred while trying to apply changes: {e}")
            self.last_proposed_changes = None
            self._display_system_message("Attempting to re-index project after error during apply process...")
            self.project_indexer.refresh_index()

    def _execute_script_in_new_terminal(self, script_path_abs: str):
        if not (self.settings and self.settings.get('admin_mode_enabled', False)):
            self._display_error("Admin mode is not enabled. Automatic script execution aborted.")
            logger.warning(f"Attempt to execute script {script_path_abs} aborted: Admin Mode OFF.")
            return

        if not isfile(script_path_abs):
            self._display_error(f"Script file not found at '{script_path_abs}'. Cannot execute.")
            logger.error(f"Execute script failed: File not found at {script_path_abs}.")
            return

        if not script_path_abs.lower().endswith(".py"):
            self._display_system_message(f"File '{basename(script_path_abs)}' is not a Python script. Automatic execution skipped.")
            logger.info(f"Skipping execution of non-Python file: {script_path_abs}")
            return

        self._display_system_message(f"Attempting to execute '{basename(script_path_abs)}' in a new terminal...")
        python_executable = sys.executable
        script_directory = dirname(script_path_abs)

        try:
            if sys.platform == "win32":
                subprocess.Popen(f'start "Python Script Output" /D "{script_directory}" cmd /K "{python_executable}" "{script_path_abs}"', shell=True)
            elif sys.platform == "darwin":
                applescript_command = (
                    f'tell application "Terminal"\n'
                    f'    activate\n'
                    f'    do script "cd \\"{script_directory}\\"; {python_executable} \\"{script_path_abs}\\"; echo \\"--- Script execution finished. Press Cmd+W to close this terminal. ---\\""\n'
                    f'end tell'
                )
                subprocess.Popen(['osascript', '-e', applescript_command])
            elif sys.platform.startswith("linux"):
                terminals = [
                    ['gnome-terminal', f'--working-directory={script_directory}', '--', python_executable, script_path_abs],
                    ['konsole', f'--workdir', script_directory, '-e', python_executable, script_path_abs],
                    ['xfce4-terminal', f'--working-directory={script_directory}', '--command', f'{python_executable} "{script_path_abs}"'],
                    ['xterm', '-e', f'cd "{script_directory}" && {python_executable} "{script_path_abs}" ; read -p "Press Enter to close terminal..."']
                ]
                executed = False
                for term_cmd_parts in terminals:
                    try:
                        subprocess.Popen(term_cmd_parts)
                        executed = True
                        self._display_system_message(f"Launched with {term_cmd_parts[0]}.")
                        break
                    except FileNotFoundError:
                        logger.debug(f"Terminal emulator {term_cmd_parts[0]} not found. Trying next.")
                        continue
                if not executed:
                    self._display_error("Could not find a known terminal emulator (gnome-terminal, konsole, xfce4-terminal, xterm) to execute the script. Please run it manually from its directory.")
                    logger.warning(f"Failed to find a suitable terminal for Linux to execute {script_path_abs}")
            else:
                self._display_error(f"Script execution in a new terminal is not automatically supported on your platform ('{sys.platform}'). Please run '{basename(script_path_abs)}' manually from its directory: {script_directory}")
        except Exception as e:
            self._display_error(f"Failed to execute script '{basename(script_path_abs)}' in a new terminal: {e}")
            logger.error(f"Error executing script {script_path_abs} in new terminal: {e}", exc_info=True)

    def _run_test_command_internal(self, command: str, command_args: Optional[List[str]] = None) -> None:
        try:
            if not command.strip():
                self._display_error("No test command configured.")
                return

            full_command = command
            if command_args:
                full_command += " " + " ".join(map(str, command_args))

            self._display_system_message(f"\nRunning command: {full_command} (in directory: {self.code_folder_path})")

            process = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.code_folder_path,
                check=False,
                encoding='utf-8',
                errors='replace'
            )

            self._display_system_message(f"--- Command Output (Exit Code: {process.returncode}) ---")
            stdout = process.stdout.strip() if process.stdout else ""
            stderr = process.stderr.strip() if process.stderr else ""

            if stdout:
                print(f"Stdout:\n{textwrap.indent(stdout, '  ')}")
            if stderr:
                self._display_error(f"Stderr:\n{textwrap.indent(stderr, '  ')}")

            if process.returncode != 0:
                self._display_error(f"--- Command FAILED (exit code {process.returncode}) ---")
            else:
                self._display_system_message(f"--- Command FINISHED SUCCESSFULLY ---")

        except FileNotFoundError:
            cmd_executable = command.split()[0]
            self._display_error(f"Failed to run test command: Executable '{cmd_executable}' not found. Ensure it's in your system's PATH or provide an absolute path.")
            logger.error(f"Test command executable '{cmd_executable}' from command '{command}' not found.")
        except OSError as e:
            self._display_error(f"OS error occurred while running test command '{command}': {e.strerror}")
            logger.error(f"OS error running test command '{command}': {e}", exc_info=True)
        except Exception as e:
            self._display_error(f"An unexpected error occurred while running test command '{command}': {e}")
            logger.error(f"Failed running test command '{command}': {e}", exc_info=True)

    def _handle_runtest_command(self, args: List[str]) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded, cannot run test command.")
                return

            test_command_template: Optional[str] = self.settings.get('test_command')
            if not test_command_template or not test_command_template.strip():
                self._display_system_message("No test command is configured. Use '/settings test_command <your_command>' to set one.")
                return

            self._run_test_command_internal(test_command_template, args)
        except Exception as e:
            logger.error(f"Error in _handle_runtest_command: {e}", exc_info=True)
            self._display_error(f"An error occurred trying to prepare or run the test command: {e}")

    def _handle_reindex_command(self, args: List[str]) -> None:
        try:
            self._display_system_message("Manually refreshing project index...")
            self.project_indexer.refresh_index()
            self._display_system_message(f"Project index for '{basename(self.code_folder_path)}/' refreshed. Found {len(self.project_indexer.file_index)} files.")
        except Exception as e:
            logger.error(f"Error during manual reindex: {e}", exc_info=True)
            self._display_error(f"Error re-indexing project: {e}")

    def _handle_find_command(self, args: List[str]) -> None:
        try:
            if not args:
                self._display_error("Usage: /find <substring_in_filepath>")
                self._display_system_message("Example: /find models.py")
                return

            search_term = " ".join(args)
            self._display_system_message(f"Searching project for paths containing '{search_term}'...")

            found_files_info = self.project_indexer.find_files_by_name_substring(search_term, top_n=20)

            if not found_files_info:
                self._display_system_message(f"No files found matching '{search_term}'.")
                return

            self._display_system_message(f"Found {len(found_files_info)} matching file(s) (displaying top {len(found_files_info)}):")
            for idx, file_info in enumerate(found_files_info):
                rel_path = file_info['relative_path']
                size_kb = file_info['size_bytes'] / 1024
                print(f"  {idx+1}. {rel_path} ({size_kb:.1f} KB)")

            self._display_system_message("Use '/add <path_from_list>' to pin files to context.")
        except Exception as e:
            logger.error(f"Error during /find: {e}", exc_info=True)
            self._display_error(f"Error searching files: {e}")

    def _handle_add_command(self, args: List[str]) -> None:
        try:
            if not args:
                self._display_error("Usage: /add <path_in_project_or_directory_name> [...]")
                self._display_system_message("Example: /add src/utils.py my_folder")
                self._display_system_message("Pins files/dirs to immediate context for the next query.")
                return

            added_to_pinned_count = 0
            skipped_count = 0
            project_root_abs = self.project_indexer.base_path

            for item_arg in args:
                item_arg_cleaned = item_arg.strip('\'"`')

                path_relative_to_project_root = abspath(join(project_root_abs, item_arg_cleaned))
                path_as_absolute_within_project = abspath(item_arg_cleaned)

                potential_item_abs_path: Optional[str] = None

                if exists(path_relative_to_project_root) and path_relative_to_project_root.startswith(project_root_abs):
                    potential_item_abs_path = path_relative_to_project_root
                elif exists(path_as_absolute_within_project) and path_as_absolute_within_project.startswith(project_root_abs):
                    potential_item_abs_path = path_as_absolute_within_project
                else:
                    found_by_find = self.project_indexer.find_files_by_name_substring(item_arg_cleaned, top_n=5)

                    if len(found_by_find) == 1:
                        potential_item_abs_path = found_by_find[0]['abs_path']
                        if not (isfile(potential_item_abs_path) or isdir(potential_item_abs_path)):
                             self._display_error(f"Found '{item_arg_cleaned}' as '{relpath(potential_item_abs_path, project_root_abs)}' but it's not a valid file or directory.")
                             potential_item_abs_path = None
                        else:
                             self._display_system_message(f"Interpreted '{item_arg_cleaned}' as '{relpath(potential_item_abs_path, project_root_abs)}'.")
                    elif len(found_by_find) > 1:
                        self._display_error(f"Path '{item_arg_cleaned}' is ambiguous. Did you mean one of these?")
                        for i, f_info in enumerate(found_by_find):
                            print(f"  {i+1}. {f_info['relative_path']} ({f_info['size_bytes']/1024:.1f} KB)")
                        self._display_system_message("Please use a more specific path or one from the list above.")
                        skipped_count += 1
                        continue

                if not potential_item_abs_path:
                    self._display_error(f"Path or item '{item_arg_cleaned}' not found in the project index or is ambiguous. Try '/find {item_arg_cleaned}'.")
                    skipped_count +=1
                    continue

                files_to_pin_this_arg: List[str] = []
                if isdir(potential_item_abs_path):
                    dir_display_name = relpath(potential_item_abs_path, project_root_abs).replace('\\','/')
                    dir_display_name = basename(project_root_abs) if dir_display_name == '.' else dir_display_name
                    self._display_system_message(f"Processing directory '{dir_display_name}' to pin its direct files...")

                    dir_rel_path_prefix = relpath(potential_item_abs_path, project_root_abs).replace('\\','/')
                    if dir_rel_path_prefix != '.':
                        dir_rel_path_prefix += '/'
                    else:
                        dir_rel_path_prefix = ""

                    found_in_dir_count = 0
                    for indexed_rel_path, file_info_dict in self.project_indexer.file_index.items():
                        if indexed_rel_path.startswith(dir_rel_path_prefix):
                            path_part_after_prefix = indexed_rel_path[len(dir_rel_path_prefix):]
                            if '/' not in path_part_after_prefix:
                                files_to_pin_this_arg.append(file_info_dict['abs_path'])
                                found_in_dir_count +=1

                    if not files_to_pin_this_arg:
                        self._display_system_message(f"No files found directly within directory '{dir_display_name}'. (Sub-directories are not recursively added).")
                    else:
                        self._display_system_message(f"Found {found_in_dir_count} file(s) in '{dir_display_name}'.")

                elif isfile(potential_item_abs_path):
                    files_to_pin_this_arg.append(potential_item_abs_path)
                else:
                    self._display_error(f"Item '{item_arg_cleaned}' resolved to '{potential_item_abs_path}' which is not a recognized file or directory in the index.")
                    skipped_count +=1
                    continue

                for abs_f_path_to_pin in files_to_pin_this_arg:
                    if abs_f_path_to_pin not in self.active_files_pinned:
                        rel_path_key_check = relpath(abs_f_path_to_pin, project_root_abs).replace('\\','/')
                        if rel_path_key_check in self.project_indexer.file_index:
                            self.active_files_pinned.add(abs_f_path_to_pin)
                            self._display_system_message(f"Pinned '{basename(abs_f_path_to_pin)}' to context.")
                            added_to_pinned_count += 1
                        else:
                            self._display_error(f"File '{basename(abs_f_path_to_pin)}' (resolved to {abs_f_path_to_pin}) is not currently in the project index. Try '/reindex'.")
                            skipped_count +=1
                    else:
                        self._display_system_message(f"File '{basename(abs_f_path_to_pin)}' is already pinned.")

            if added_to_pinned_count > 0:
                self._display_system_message(f"Successfully pinned {added_to_pinned_count} file(s) to the context for the next query.")
            if skipped_count > 0:
                self._display_error(f"Skipped or failed to pin {skipped_count} item(s). Please check paths or use '/find'.")
            if not added_to_pinned_count and not skipped_count and args:
                 self._display_system_message("No new files were pinned (items might have been already pinned or not found).")

        except Exception as e:
            logger.error(f"Error in _handle_add_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while trying to pin files: {e}")

    def _handle_drop_command(self, args: List[str]) -> None:
        try:
            if not args:
                self._display_error("Usage: /drop <filename_or_pinned_path_substring_or_all> [...]")
                self._display_system_message("Example: /drop utils.py specific/file.txt all")
                self._display_system_message("Unpins specified files or all files from the immediate context.")
                return

            if not self.active_files_pinned:
                self._display_system_message("No files are currently pinned.")
                return

            dropped_from_pinned_count: int = 0

            if len(args) == 1 and args[0].lower() == 'all':
                dropped_from_pinned_count = len(self.active_files_pinned)
                self.active_files_pinned.clear()
                self._display_system_message(f"Unpinned all {dropped_from_pinned_count} file(s).")
                return

            current_pinned_abs_paths: List[str] = list(self.active_files_pinned)
            files_to_unpin_resolved_abs: Set[str] = set()
            skipped_args: List[str] = []

            for arg_identifier_to_drop in args:
                found_match_for_arg = False
                norm_arg_id_lower = arg_identifier_to_drop.lower().replace('\\','/')

                for pinned_abs_path in current_pinned_abs_paths:
                    if pinned_abs_path in files_to_unpin_resolved_abs:
                        continue

                    pinned_basename_lower = basename(pinned_abs_path).lower()
                    try:
                        pinned_rel_path_lower = relpath(pinned_abs_path, self.project_indexer.base_path).lower().replace('\\','/')
                    except ValueError:
                        pinned_rel_path_lower = pinned_basename_lower

                    if norm_arg_id_lower == pinned_basename_lower or \
                       norm_arg_id_lower == pinned_rel_path_lower or \
                       norm_arg_id_lower in pinned_rel_path_lower or \
                       norm_arg_id_lower in pinned_basename_lower:

                        files_to_unpin_resolved_abs.add(pinned_abs_path)
                        self._display_system_message(f"Marked '{basename(pinned_abs_path)}' for unpinning based on '{arg_identifier_to_drop}'.")
                        found_match_for_arg = True

                if not found_match_for_arg:
                    skipped_args.append(arg_identifier_to_drop)

            if files_to_unpin_resolved_abs:
                self.active_files_pinned -= files_to_unpin_resolved_abs
                dropped_from_pinned_count = len(files_to_unpin_resolved_abs)
                self._display_system_message(f"Successfully unpinned {dropped_from_pinned_count} file(s).")

            if skipped_args:
                self._display_error(f"Could not find or unpin based on: {', '.join(skipped_args)}. Check pinned files with /list.")

            if not files_to_unpin_resolved_abs and not skipped_args and args:
                self._display_system_message("No files were unpinned based on the arguments provided.")

        except Exception as e:
            logger.error(f"Error in _handle_drop_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while trying to unpin files: {e}")

    def _handle_list_command(self, args: List[str]) -> None:
        try:
            num_indexed_files = len(self.project_indexer.file_index)
            self._display_system_message(f"Project Index: {num_indexed_files} files indexed in '{basename(self.code_folder_path)}/'.")

            if self.active_files_pinned:
                self._display_system_message("\nCurrently Pinned Files (will be included in AI context):")
                sorted_pinned_abs_paths = sorted(list(self.active_files_pinned))

                total_pinned_size_bytes = 0

                for idx, abs_pinned_path in enumerate(sorted_pinned_abs_paths):
                    try:
                        rel_display_path = relpath(abs_pinned_path, self.project_indexer.base_path).replace('\\','/')

                        file_size_bytes = -1
                        if exists(abs_pinned_path) and isfile(abs_pinned_path):
                            file_size_bytes = getsize(abs_pinned_path)
                            total_pinned_size_bytes += file_size_bytes

                        size_str = f"({file_size_bytes / 1024:.1f} KB)" if file_size_bytes >=0 else "(size N/A or file missing)"
                        print(f"  {idx+1}. {rel_display_path} {size_str}")
                    except ValueError:
                        print(f"  {idx+1}. {abs_pinned_path} (Error: Path seems outside project for relative display)")
                    except OSError as e_size:
                        print(f"  {idx+1}. {basename(abs_pinned_path)} (Error getting size: {e_size.strerror})")

                total_pinned_size_kb = total_pinned_size_bytes / 1024
                self._display_system_message(f"Total size of pinned files: {total_pinned_size_kb:.1f} KB.")
                if total_pinned_size_bytes > MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT * 0.8 :
                     self._display_system_message(f"{Fore.YELLOW}Warning: Total size of pinned files is approaching context limit ({MAX_TOTAL_FILE_CONTENT_CHARS_IN_PROMPT / 1024:.0f} KB). Some content may be truncated or summarized.{Style.RESET_ALL}")

            else:
                self._display_system_message("\nNo files currently pinned. Use '/add <path>' to add files, or '/find <name>' to search for files.")
        except Exception as e:
            logger.error(f"Error listing files: {e}", exc_info=True)
            self._display_error(f"Could not display the list of pinned files: {e}")

    def _handle_discard_command(self, args: List[str]) -> None:
        try:
            if self.last_proposed_changes:
                self.last_proposed_changes = None
                self._display_system_message("Proposed code changes have been discarded.")
                logger.info("User discarded proposed AI code changes.")
            else:
                self._display_system_message("No proposed changes are currently available to discard.")
        except Exception as e:
            logger.error(f"Error discarding changes: {e}", exc_info=True)
            self._display_error("An error occurred while trying to discard changes.")

    def _handle_model_command(self, args: List[str]) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded, cannot manage AI models.")
                return

            available_models_info = {name: cfg for name, cfg in helper.SUPPORTED_MODELS.items() if cfg.get("client")}
            available_model_names = list(available_models_info.keys())

            if not args:
                 current_model_name = self.settings.get('model_name', 'N/A')
                 self._display_system_message(f"Current AI model client: {Fore.GREEN}{current_model_name}{Style.RESET_ALL}")
                 if available_model_names:
                     self._display_system_message(f"Available model clients: {', '.join(available_model_names)}")
                 else:
                     self._display_error("No AI model clients are currently available. Please check API key configurations and logs.")
                 self._display_system_message("Usage: /model <client_name_from_list>")
                 return

            new_model_client_name = args[0].lower()
            if new_model_client_name in available_model_names:
                self.settings['model_name'] = new_model_client_name
                database.save_settings(self.conn, self.settings)
                self._display_system_message(f"AI model client set to: {Fore.GREEN}{new_model_client_name}{Style.RESET_ALL}")
                logger.info(f"User changed AI model client to {new_model_client_name}")
            elif new_model_client_name in helper.SUPPORTED_MODELS:
                self._display_error(f"Model client '{new_model_client_name}' is configured but currently unavailable (e.g., missing API key or initialization error). Please check logs.")
            else:
                self._display_error(f"Unsupported model client: '{new_model_client_name}'.")
                if available_model_names:
                    self._display_system_message(f"Available options: {', '.join(available_model_names)}")
                else:
                    self._display_system_message("No model clients are currently available.")
        except Exception as e:
            logger.error(f"Error in _handle_model_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while managing AI models: {e}")

    def _handle_settings_command(self, args: List[str]) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded.")
                return

            display_order = ["model_name", "admin_mode_enabled", "temperature", "test_command"]

            if len(args) == 0 or (len(args) == 1 and args[0].lower() in ["show", "view", "list"]):
                self._display_system_message("Current application settings:")
                for key in display_order:
                    value = self.settings.get(key)
                    display_value_str: str
                    if key == 'admin_mode_enabled':
                        display_value_str = f"{Fore.GREEN}ON{Style.RESET_ALL}" if value else f"{Fore.RED}OFF{Style.RESET_ALL}"
                    elif key == 'test_command':
                        display_value_str = f"'{value}'" if value else f"{Fore.DIM}Not set{Style.RESET_ALL}"
                    elif key == 'model_name':
                        display_value_str = f"{Fore.GREEN}{value}{Style.RESET_ALL}" if value else f"{Fore.DIM}Not set{Style.RESET_ALL}"
                    elif isinstance(value, float):
                        display_value_str = f"{value:.2f}"
                    elif value is None:
                        display_value_str = f"{Fore.DIM}Not set{Style.RESET_ALL}"
                    else:
                        display_value_str = str(value)
                    print(f"  {key:<20}: {display_value_str}")
                self._display_system_message(f"\nUse '/settings <key> <value>' to change a setting.")
                self._display_system_message(f"Example: /settings temperature 0.7")
                self._display_system_message(f"To clear test_command: /settings test_command none")
                return

            if len(args) == 2:
                key_to_set = args[0].lower()
                value_to_set_str = args[1]

                if key_to_set not in display_order:
                    self._display_error(f"Unknown setting key: '{key_to_set}'. Valid keys are: {', '.join(display_order)}")
                    return

                current_settings_copy = self.settings.copy()
                new_value: Any = value_to_set_str

                if key_to_set == "temperature":
                    try:
                        new_value = float(value_to_set_str)
                        if not (0.0 <= new_value <= 2.0):
                             self._display_error("Invalid temperature value. Must be a number, usually between 0.0 and 2.0.")
                             return
                    except ValueError:
                        self._display_error("Invalid temperature value. Must be a number.")
                        return
                elif key_to_set == "admin_mode_enabled":
                    if value_to_set_str.lower() in ['true', 'on', '1', 'yes', 'enable']:
                        new_value = True
                    elif value_to_set_str.lower() in ['false', 'off', '0', 'no', 'disable']:
                        new_value = False
                    else:
                        self._display_error("Invalid value for admin_mode_enabled. Use 'on'/'off', 'true'/'false', etc.")
                        return
                elif key_to_set == "test_command":
                    new_value = value_to_set_str if value_to_set_str.lower() not in ["none", "clear", "null", ""] else None
                elif key_to_set == "model_name":
                    available_model_names = [name for name, cfg in helper.SUPPORTED_MODELS.items() if cfg.get("client")]
                    if value_to_set_str.lower() not in available_model_names:
                        self._display_error(f"Invalid model client '{value_to_set_str}'. Available: {', '.join(available_model_names) if available_model_names else 'None'}")
                        return
                    new_value = value_to_set_str.lower()

                current_settings_copy[key_to_set] = new_value
                database.save_settings(self.conn, current_settings_copy)
                self.settings = current_settings_copy
                self._display_system_message(f"Setting '{key_to_set}' has been updated to '{new_value if new_value is not None else 'Not set'}'.")

            elif len(args) == 1 and args[0].lower() in display_order:
                value = self.settings.get(args[0].lower())
                self._display_system_message(f"{args[0].lower()}: {value if value is not None else 'Not set'}")

            else:
                self._display_error("Invalid usage. To view all: /settings. To set: /settings <key> <value>.")
                return
        except Exception as e:
            logger.error(f"Error in _handle_settings_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while managing settings: {e}")

    def _handle_codefolder_command(self, args: List[str]) -> None:
        try:
            self._display_system_message(f"Current Code Folder (Project Root for indexing):")
            try:
                relative_p = relpath(self.code_folder_path, os.getcwd())
            except ValueError:
                relative_p = "(Path is on a different drive or cannot be made relative to current location)"

            self._display_system_message(f"  Relative to current dir: {relative_p}")
            self._display_system_message(f"  Absolute path: {self.code_folder_path}")

            if not exists(self.code_folder_path):
                self._display_error("Warning: The configured Code Folder path does not currently exist on the filesystem.")
            elif not os.path.isdir(self.code_folder_path):
                self._display_error("Warning: The configured Code Folder path exists but is not a directory.")
            else:
                self._display_system_message(f"Status: Path exists and is a directory.")

        except Exception as e:
            logger.error(f"Error in _handle_codefolder_command: {e}", exc_info=True)
            self._display_error(f"An error occurred displaying the code folder path: {e}")

    def _handle_admin_command(self, args: List[str]) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded, cannot toggle Admin Mode.")
                return

            current_status: bool = bool(self.settings.get('admin_mode_enabled', False))
            new_status: Optional[bool] = None
            action_msg_verb = "Toggled"

            if not args:
                new_status = not current_status
            elif args[0].lower() in ['on', 'true', 'enable', '1', 'yes']:
                new_status = True
                action_msg_verb = "Set"
            elif args[0].lower() in ['off', 'false', 'disable', '0', 'no']:
                new_status = False
                action_msg_verb = "Set"
            else:
                self._display_error("Invalid argument. Usage: /sudo [on|off] (or just /sudo to toggle).")
                return

            if new_status == current_status and args:
                self._display_system_message(f"Admin Mode is already {f'{Fore.GREEN}ON{Style.RESET_ALL}' if current_status else f'{Fore.RED}OFF{Style.RESET_ALL}'}. No change made.")
                return

            self.settings['admin_mode_enabled'] = new_status
            database.save_settings(self.conn, self.settings)

            final_status_text = f"{Fore.GREEN}ON{Style.RESET_ALL}" if new_status else f"{Fore.RED}OFF{Style.RESET_ALL}"
            self._display_system_message(f"{action_msg_verb} Admin Mode to: {final_status_text}")

            if new_status:
                self._display_system_message(f"{Fore.YELLOW}Warning: Admin Mode is now ON. This allows the AI to propose and potentially execute filesystem operations or run commands (like tests). Use with caution and review all actions.{Style.RESET_ALL}")
            else:
                self._display_system_message("Admin Mode is OFF. AI capabilities for direct system changes are restricted.")

            logger.info(f"Admin Mode changed by user to {new_status}.")
        except Exception as e:
            logger.error(f"Error in _handle_admin_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while toggling Admin Mode: {e}")

    def _notify_proposed_changes(self, proposed_changes: Dict[str, Dict[str, Any]]):
        try:
            if not proposed_changes: return

            num_unique_files_affected = len(set(pc_info['target_path_abs'] for pc_info in proposed_changes.values()))

            change_types_summary = {'new': 0, 'modified': 0}
            for pc_info in proposed_changes.values():
                if pc_info['is_new']:
                    change_types_summary['new'] += 1
                else:
                    change_types_summary['modified'] += 1

            summary_parts = []
            if change_types_summary['new'] > 0:
                summary_parts.append(f"{change_types_summary['new']} new file(s)")
            if change_types_summary['modified'] > 0:
                summary_parts.append(f"{change_types_summary['modified']} existing file(s) to be modified")

            summary_text = ", ".join(summary_parts) if summary_parts else "no specific file changes identified"

            self._display_system_message(f"\n--- AI proposed code changes involving {num_unique_files_affected} file(s) ---")
            self._display_system_message(f"Details: {summary_text}.")
            self._display_system_message(f"Use {Fore.YELLOW}/apply{Style.RESET_ALL} to review and apply these changes (Python files will auto-execute if Admin Mode is ON), or {Fore.YELLOW}/discard{Style.RESET_ALL} to ignore them.")
        except Exception as e:
            logger.error(f"Error notifying proposed changes: {e}", exc_info=True)
            self._display_error("An issue occurred while summarizing proposed changes.")

    def _handle_message(self, user_message: str) -> None:
        try:
            if not self.settings:
                self._display_error("Settings not loaded, cannot process message.")
                return

            model_name: str = self.settings.get('model_name', 'gemini')

            if model_name not in helper.SUPPORTED_MODELS or not helper.SUPPORTED_MODELS[model_name].get("client"):
                available_models = [name for name, config in helper.SUPPORTED_MODELS.items() if config.get("client")]
                if available_models:
                    fallback_model = available_models[0]
                    self._display_error(f"Currently selected AI model '{model_name}' is unavailable. Switching to the first available model: '{fallback_model}'.")
                    logger.warning(f"Model '{model_name}' was unavailable. Falling back to '{fallback_model}'.")
                    self.settings['model_name'] = fallback_model
                    database.save_settings(self.conn, self.settings)
                    model_name = fallback_model
                else:
                    self._display_error("FATAL: No AI models are currently available or initialized. Please check API key configurations and application logs.")
                    logger.critical("No AI models available for processing user message.")
                    return

            self._display_system_message(f"Sending request to {model_name} (focus: code assistance)...")

            content_parts: List[helper.GoogleGenAIContentType] = self._build_prompt_with_context(user_message)

            if content_parts and isinstance(content_parts[0], str) and content_parts[0].startswith(f"{Fore.RED}Error:"):
                print(content_parts[0])
                return

            response_text: str = helper.chat_with_model(content_parts, model_name=model_name, mode_hint='code')

            if response_text is None:
                self._display_error(f"Received no response from the AI model ({model_name}).")
                logger.error(f"helper.chat_with_model returned None for model {model_name}.")
                return
            elif response_text.startswith("Error:"):
                self._display_error(f"AI/API Error: {response_text.replace('Error: ', '', 1)}")
                return

            self._display_agent_message(response_text)

            proposed_changes = self._parse_llm_response_for_changes(response_text)
            if proposed_changes:
                self._notify_proposed_changes(proposed_changes)
        except Exception as e:
            logger.exception(f"A core error occurred in _handle_message: {e}")
            self._display_error(f"An unexpected error occurred while processing your message: {e}")

    def _handle_command(self, user_input: str) -> bool:
        try:
            parts: List[str] = user_input.strip().split()
            if not parts:
                return True

            command: str = parts[0].lower()
            args: List[str] = parts[1:]

            command_mapping: Dict[str, Any] = {
                "/help": self._handle_help_command,
                "/quit": lambda a: False,
                "/exit": lambda a: False,
                "/clear": self._handle_clear_command,
                "/add": self._handle_add_command,
                "/drop": self._handle_drop_command,
                "/list": self._handle_list_command,
                "/apply": self._review_and_apply_changes,
                "/discard": self._handle_discard_command,
                "/model": self._handle_model_command,
                "/settings": self._handle_settings_command,
                "/codefolder": self._handle_codefolder_command,
                "/sudo": self._handle_admin_command,
                "/runtest": self._handle_runtest_command,
                "/reindex": self._handle_reindex_command,
                "/find": self._handle_find_command,
            }
            if stream:
                command_mapping["/capture_context"] = self._handle_capture_context_command

            handler = command_mapping.get(command)
            if handler:
                result = handler(args)
                return result if isinstance(result, bool) else True
            else:
                self._display_error(f"Unknown command: '{command}'. Type /help for a list of available commands.")
                return True
        except Exception as e:
            logger.exception(f"Error executing command '{user_input.split()[0] if user_input else 'EMPTY_INPUT'}': {e}")
            self._display_error(f"An internal error occurred while processing the command. Please check logs for details.")
            return True

    def _setup_voice_input(self):
        try:
            self.voice_handler = VoiceCommandHandler()
            logger.info("VoiceCommandHandler initialized successfully.")
        except ImportError:
            logger.warning("voice_input.py or its dependencies (e.g., SpeechRecognition) not found. Voice input disabled.")
            self.voice_handler = None
        except Exception as e:
            logger.error(f"Failed to initialize VoiceCommandHandler: {e}. Voice commands disabled.", exc_info=True)
            self.voice_handler = None

    def _on_voice_hotkey_pressed(self):
        if not self.voice_handler:
            msg = "\r(Voice system not active) "
            try:
                sys.stdout.write(msg + ' ' * (os.get_terminal_size().columns - len(msg)) + '\n')
                sys.stdout.flush()
                self._display_prompt()
            except Exception:
                pass
            return

        try:
            sys.stdout.write('\r(Listening for voice command...)' + ' ' * (os.get_terminal_size().columns - 30) + '\n')
            sys.stdout.flush()

            transcribed_text = self.voice_handler.listen_and_transcribe()

            if transcribed_text:
                self._display_system_message(f"Voice transcribed: '{transcribed_text}' Processing...")
                self._process_input_as_if_typed(transcribed_text)
            else:
                self._display_prompt()

        except Exception as e:
            logger.error(f"Error during voice transcription or hotkey handling: {e}", exc_info=True)
            self._display_error(f"Voice input error: {e}")
            self._display_prompt()

    def _process_input_as_if_typed(self, text_input: str):
        if not isinstance(text_input, str) or not text_input.strip():
            logger.info("Empty or invalid input received from voice transcription.")
            self._display_prompt()
            return

        print(f"{Fore.LIGHTBLACK_EX}(Voice input: {text_input}){Style.RESET_ALL}")

        if text_input.startswith('/'):
            if not self._handle_command(text_input):
                if text_input.lower() in ["/quit", "/exit"]:
                    pass
        else:
            self._handle_message(text_input)

        self._display_prompt()

    def _setup_keyboard_shortcuts(self):
        if not keyboard:
            logger.warning("Keyboard module not available. Global hotkeys disabled.")
            return
        if not self.voice_handler:
             logger.info("Voice input system not configured/failed to init, skipping hotkey setup.")
             return

        try:
            shortcut = "ctrl+shift+v"
            keyboard.add_hotkey(shortcut, self._on_voice_hotkey_pressed, suppress=True)
            self.hotkeys_active = True
            logger.info(f"Voice command hotkey '{shortcut}' registered.")
        except RuntimeError as rte:
            self.hotkeys_active = False
            logger.error(f"Failed to set up keyboard shortcut ('{shortcut}') due to RuntimeError: {rte}. This might be due to running in an environment without a display server (e.g., some SSH sessions or headless systems), or permissions issues.", exc_info=True)
        except Exception as e:
            self.hotkeys_active = False
            logger.error(f"Failed to set up keyboard shortcut ('{shortcut}'): {e}", exc_info=True)

    def _handle_capture_context_command(self, args: List[str]) -> None:
        try:
            if not stream:
                self._display_error("Screen capture module (stream.py) not available or failed to import.")
                return

            user_text_prompt = " ".join(args) if args else "Analyze this screenshot, focusing on any visible code, UI elements, or error messages."
            self._display_system_message("Capturing screen...")

            result_container = {"image_data": None, "error": None}

            def capture_task_sync_wrapper():
                try:
                    grabber = stream.ScreenGrabber()
                    image_dict = asyncio.run(grabber.capture_screen_base64_async(output_format="JPEG"))

                    if image_dict and "data" in image_dict and "mime_type" in image_dict:
                        result_container["image_data"] = image_dict
                    else:
                        errmsg = "Failed to capture screen or received malformed image data."
                        logger.error(errmsg + f" Image dict from grabber: {image_dict}")
                        result_container["error"] = errmsg
                except Exception as e_task:
                    logger.error(f"Exception during screen capture task: {e_task}", exc_info=True)
                    result_container["error"] = str(e_task)

            capture_thread = threading.Thread(target=capture_task_sync_wrapper)
            capture_thread.start()
            capture_thread.join(timeout=15)

            if capture_thread.is_alive():
                self._display_error("Screen capture operation timed out.")
                logger.error("Screen capture thread timed out.")
                return

            if result_container["error"]:
                self._display_error(f"Screen capture failed: {result_container['error']}")
                return

            image_data_dict = result_container["image_data"]
            if not image_data_dict:
                self._display_error("Screen capture failed to return image data.")
                return

            self._display_system_message("Screen captured successfully. Sending to AI for analysis...")

            content_parts: List[helper.GoogleGenAIContentType] = [user_text_prompt, image_data_dict]

            current_model_name = self.settings.get('model_name', 'gemini') if self.settings else 'gemini'
            model_to_use_for_multimodal = current_model_name

            if model_to_use_for_multimodal != "gemini":
                logger.warning(f"Current model '{current_model_name}' may not support multimodal input. Attempting with Gemini for screen capture analysis.")
                if "gemini" in helper.SUPPORTED_MODELS and helper.SUPPORTED_MODELS["gemini"].get("client"):
                    model_to_use_for_multimodal = "gemini"
                else:
                    self._display_error("Gemini model (required for screen capture analysis) is not available. Please configure Gemini API key.")
                    return

            ai_response = helper.chat_with_model(
                user_content_parts=content_parts,
                model_name=model_to_use_for_multimodal,
                mode_hint='conversation'
            )

            if ai_response:
                if ai_response.startswith("Error:"):
                    self._display_error(f"AI Error during screen analysis: {ai_response.replace('Error: ', '', 1)}")
                else:
                    self._display_agent_message(f"AI Analysis of Screenshot:\n{ai_response}")
                    proposed_changes = self._parse_llm_response_for_changes(ai_response)
                    if proposed_changes:
                        self._notify_proposed_changes(proposed_changes)
            else:
                self._display_error("No response received from AI for the screen capture analysis.")
        except Exception as e:
            logger.error(f"Error in _handle_capture_context_command: {e}", exc_info=True)
            self._display_error(f"An error occurred while processing the screen capture command: {e}")

    def _print_startup_info(self, show_full_logo: bool = True):
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            if show_full_logo:
                print(f"\n\n\t\t\t\t\t\t\t\t      {Fore.YELLOW}~{Style.RESET_ALL} Indexed")

            print(f"\n\t\t\t\t     Type '{Fore.YELLOW}/help{Style.RESET_ALL}' for commands, '{Fore.YELLOW}/exit{Style.RESET_ALL}' to quit")

            if not self.settings:
                print(f"{Fore.RED}{Style.BRIGHT}Error: Settings not loaded. Startup information may be incomplete.{Style.RESET_ALL}")
                return

            current_model_client: str = self.settings.get('model_name', 'N/A')
            try:
                relative_code_folder: str = relpath(self.code_folder_path, os.getcwd())
            except ValueError:
                relative_code_folder = self.code_folder_path

            num_indexed_files_str = "N/A"
            if self.project_indexer and self.project_indexer.file_index is not None:
                num_indexed_files_str = str(len(self.project_indexer.file_index))

            print(f"\n\t\t\t\t\t\t\t       AI Model: {Fore.YELLOW}{current_model_client}{Style.RESET_ALL}"
                  f"\n\n\t\t\t\t\t\t\t   Enviorment: {Fore.YELLOW}{relative_code_folder}{Style.RESET_ALL} [{Fore.YELLOW}{num_indexed_files_str}{Style.RESET_ALL}]")

            if keyboard:
                if self.voice_handler and self.hotkeys_active:
                    self._display_system_message(f"\n\t\t\t\t\t\t\t   {Style.RESET_ALL}Listen: {Fore.YELLOW}Ctrl+Shift+V{Style.RESET_ALL}")
                elif self.voice_handler and not self.hotkeys_active:
                    self._display_error(f"Voice input hotkey {Fore.CYAN}Ctrl+Shift+V{Style.RESET_ALL} FAILED to activate (check logs/permissions). Voice input via hotkey is disabled.")
                elif not self.voice_handler:
                    self._display_system_message(f"Voice input system could not be initialized (e.g., missing SpeechRecognition). Hotkey {Fore.CYAN}Ctrl+Shift+V{Style.RESET_ALL} is disabled.")
            else:
                self._display_system_message(f"Keyboard module not available. Hotkeys (including for voice input) are disabled.")

            print("")

        except Exception as e:
            logger.error(f"Error printing startup info: {e}", exc_info=True)
            print(f"{Fore.RED}{Style.BRIGHT}Error displaying critical startup information.{Style.RESET_ALL}")

    def _handle_help_command(self, args: List[str]) -> None:
        if not self.command_list:
            self._display_system_message("Available commands:")
            print(f"  {Style.DIM}No commands available.{Style.RESET_ALL}")
            return

        sorted_commands = sorted(self.command_list.items())
        num_commands = len(sorted_commands)
        items_per_page = 5
        num_pages = (num_commands + items_per_page - 1) // items_per_page
        
        if num_pages == 0:
            num_pages = 1

        current_page = 1

        max_cmd_len = 0
        if sorted_commands:
            for cmd, _ in sorted_commands:
                if len(cmd) > max_cmd_len:
                    max_cmd_len = len(cmd)
        command_col_width = max_cmd_len

        while True:
            os.system('cls' if os.name == 'nt' else 'clear') 
            
            self._display_system_message(f"Available commands (Page {current_page} of {num_pages}):")

            start_index = (current_page - 1) * items_per_page
            end_index = start_index + items_per_page
            current_page_commands = sorted_commands[start_index:end_index]

            for command, full_description in current_page_commands:
                usage_part = ""
                description_part = full_description
                
                usage_marker = "Usage: "
                usage_idx = full_description.find(usage_marker)

                if usage_idx > 0:
                    description_part = full_description[:usage_idx].strip()
                    usage_part = full_description[usage_idx:].strip()
                elif full_description.startswith(usage_marker): 
                    description_part = ""
                    usage_part = full_description.strip()

                cmd_formatted = f"{Fore.GREEN}{command:<{command_col_width}}{Style.RESET_ALL}"
                
                if description_part:
                    print(f"  {cmd_formatted} : {description_part}")
                else:
                    print(f"  {cmd_formatted} :")

                if usage_part:
                    usage_indent_spaces = " " * (2 + command_col_width + 3)
                    print(f"{usage_indent_spaces}{Style.DIM}{usage_part}{Style.RESET_ALL}")
            
            print("-" * 20)

            nav_options = []
            if current_page > 1:
                nav_options.append(f"[{Fore.YELLOW}P{Style.RESET_ALL}]revious")
            if current_page < num_pages:
                nav_options.append(f"[{Fore.YELLOW}N{Style.RESET_ALL}]ext")
            nav_options.append(f"[{Fore.YELLOW}Q{Style.RESET_ALL}]uit Help")
            
            if not nav_options:
                 nav_options.append(f"[{Fore.YELLOW}Q{Style.RESET_ALL}]uit Help")


            print("Options: " + " | ".join(nav_options))
            
            try:
                choice = input("Help Menu > ").lower().strip()
            except EOFError:
                choice = 'q'
                print("q")
            except KeyboardInterrupt:
                choice = 'q'
                print("\nExiting help menu...")


            if choice == 'n':
                if current_page < num_pages:
                    current_page += 1
                else:
                    print(f"{Fore.RED}Already on the last page.{Style.RESET_ALL}")
                    time.sleep(1)
            elif choice == 'p':
                if current_page > 1:
                    current_page -= 1
                else:
                    print(f"{Fore.RED}Already on the first page.{Style.RESET_ALL}")
                    time.sleep(1)
            elif choice == 'q':
                os.system('cls' if os.name == 'nt' else 'clear')
                if hasattr(self, '_print_startup_info'):
                    self._print_startup_info(show_full_logo=False)
                break
            else:
                print(f"{Fore.RED}Invalid option. Please choose from the available letters.{Style.RESET_ALL}")
                time.sleep(1.5)

    def _handle_clear_command(self, args: List[str]) -> None:
        os.system('cls' if os.name == 'nt' else 'clear')
        self._print_startup_info(show_full_logo=False)

    def start(self) -> None:
        should_exit = False
        try:
            if not self.settings:
                logger.critical("ChatBot.start: Settings not loaded. Application cannot continue.")
                print(f"{Fore.RED}{Style.BRIGHT}FATAL: Essential application settings could not be loaded. Check logs.{Style.RESET_ALL}")
                return

            current_model_client: str = self.settings.get('model_name', 'gemini')
            if current_model_client not in helper.SUPPORTED_MODELS or not helper.SUPPORTED_MODELS[current_model_client].get("client"):
                available_models = [name for name, cfg in helper.SUPPORTED_MODELS.items() if cfg.get("client")]
                if available_models:
                    fallback_model = available_models[0]
                    self._display_system_message(f"Warning: Initially selected AI model '{current_model_client}' is unavailable. Switching to '{fallback_model}'.")
                    logger.warning(f"Startup: Model '{current_model_client}' unavailable. Falling back to '{fallback_model}'.")
                    self.settings['model_name'] = fallback_model
                    database.save_settings(self.conn, self.settings)
                else:
                    logger.critical("Startup: No AI models are available. Application functionality will be severely limited or non-functional.")
                    self._display_error("FATAL: No AI models are available. Please check API key configurations and application logs. Exiting.")
                    return

            self._print_startup_info(show_full_logo=True)

            while not should_exit:
                try:
                    self._display_prompt()
                    user_input: str = input()
                except EOFError:
                    print("\nExiting (EOF received)...")
                    should_exit = True
                    break
                except KeyboardInterrupt:
                    print("\nExiting (KeyboardInterrupt)...")
                    should_exit = True
                    break

                if not user_input.strip():
                    continue

                if user_input.startswith('/'):
                    if not self._handle_command(user_input):
                        should_exit = True
                else:
                    self._handle_message(user_input)

        except SystemExit as se:
            logger.info(f"Application exiting due to SystemExit: {se}")
            should_exit = True
        except Exception as e:
            logger.critical(f"Critical unhandled error in ChatBot main loop: {e}", exc_info=True)
            self._display_error(f"A critical error occurred: {e}. Please check logs. The application may need to exit.")

        finally:
            if keyboard and self.hotkeys_active:
                try:
                    logger.info("Attempting to unregister all active hotkeys...")
                    keyboard.unhook_all_hotkeys()
                    logger.info("Hotkeys unregistered successfully.")
                except Exception as e_hotkey_remove:
                    logger.error(f"Error during unregistration of hotkeys: {e_hotkey_remove}", exc_info=True)

            if self.conn:
                try:
                    self.conn.close()
                    logger.info("Database connection closed.")
                except Exception as e_db_close:
                    logger.error(f"Error closing database connection: {e_db_close}", exc_info=True)

            print(f"\n{Fore.MAGENTA}AI Coding Assistant session ended.{Style.RESET_ALL}")
