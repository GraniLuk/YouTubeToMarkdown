from setuptools import setup, find_packages

setup(
    name="yt2md",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "google-genai>=1.16.0",
        "requests",
        "python-dotenv",
        "google-auth-oauthlib",
        "google-api-python-client",
        "pytube",
        "youtube-transcript-api",
        "pyyaml",
        "colorama>=0.4.6"
    ],
    entry_points={
        "console_scripts": [
            "yt2md=yt2md.cli:main",
        ],
    },
    author="GraniLuk",
    description="Convert YouTube videos to markdown summaries",
    long_description=open("README.md", 'r', encoding='utf-8').read(),
    long_description_content_type="text/markdown",
)
