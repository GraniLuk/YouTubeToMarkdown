from setuptools import setup, find_packages

setup(
    name="yt2md",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "google-generativeai",
        "requests",
        "python-dotenv",
        "google-auth-oauthlib",
        "google-api-python-client",
        "pytube",
        "youtube-transcript-api",
    ],
    entry_points={
        "console_scripts": [
            "yt2md=yt2md.cli:main",
        ],
    },
    author="GraniLuk",
    description="Convert YouTube videos to markdown summaries",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)
