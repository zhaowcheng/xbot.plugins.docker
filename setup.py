"""
Setuptools build hook.
"""

import re

from setuptools import setup


def _build_long_description() -> str:
    """
    Build the bilingual package description.

    :return: Combined Markdown description.
    """
    parts = []
    for readme in ('README.md', 'README.zh.md'):
        with open(readme, encoding='utf8') as readme_file:
            parts.append(''.join(readme_file.readlines()[6:]))
    description = '\n***\n\n'.join(parts)
    with open(
        'xbot/plugins/docker/version.py',
        encoding='utf8',
    ) as version_file:
        match = re.search(
            r"__version__[^'\"\\]+['\"]([^'\"]+)",
            version_file.read(),
        )
        version = match.group(1) if match else '0.1.0'
    return description.replace(
        '/tree/master/',
        f'/tree/v{version}/',
    )


setup(
    long_description=_build_long_description(),
    long_description_content_type='text/markdown',
)
