"""PreToolUse guard: plain file work only; no version-control tools or metadata.
User rules: 2026-11-01 (SVN) and 2026-11-02 (Git, overrides the earlier read-only Git allowance).
- No git commands at all (status/diff/log/show/blame/ls-files included), no gh, no Git GUIs; no access to any .git directory.
- No svn commands, no .svn metadata, no SVN auth cache (Subversion).
Plain files (including .gitignore / .gitattributes) and D:/SVN plain files stay allowed.
Exit 2 blocks the tool call; unparseable input fails closed."""
import json, re, sys

SEP = r'(^|[\s;&|(`"\'/\\])'
BLOCK = [
    (SEP + r'git(\.exe)?(["\']?)(\s|$)', 'git command'),
    (r'git\.exe', 'git.exe'),
    (SEP + r'gh(\.exe)?(["\']?)(\s|$)', 'GitHub CLI (gh)'),
    (r'tortoisegit|\bgitk\b|git-gui|lazygit|github desktop', 'Git GUI tool'),
    (r'(^|[\\/\s"\'=])\.git([\\/\s"\']|$)', '.git metadata'),
    (SEP + r'svn(\.exe)?(["\']?)(\s|$)', 'svn command'),
    (r'svn\.exe', 'svn.exe'),
    (r'tortoise(svn|proc)', 'TortoiseSVN'),
    (r'(^|[\\/\s"\'=])\.svn([\\/\s"\']|$)', '.svn metadata'),
    (r'subversion([\\/\s"\']|$)', 'SVN auth cache/config (Subversion)'),
    (r'\bsvnserve\b|\bsvnadmin\b|\bsvnlook\b|\bsvnsync\b', 'svn tools'),
]


def deny(msg):
    sys.stderr.write('BLOCKED: ' + msg + '. Rule: plain file operations only; no git/svn commands, '
                     'no .git/.svn metadata, no SVN auth cache. Ask the user (or Codex) for history.\n')
    sys.exit(2)


try:
    data = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))
except Exception:
    deny('cannot parse tool input (guard fails closed)')
ti = data.get('tool_input') or {}
text = ' '.join(str(ti.get(k, '')) for k in ('command', 'file_path', 'path', 'pattern', 'glob', 'notebook_path'))
for pat, what in BLOCK:
    if re.search(pat, text, re.IGNORECASE):
        deny(what)
sys.exit(0)
