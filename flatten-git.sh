#!/usr/bin/env zsh
set -euo pipefail

# This script flattens the Git history of the current directory
# and force-pushes it to a remote repository as a single commit.

# --- Configuration ---
REMOTE_URL="https://github.com/zachrattner/lightwall.git"
COMMIT_MESSAGE="Initial commit"
BRANCH_NAME="main"

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Main Logic ---
echo "\nStarting repository flatten process..."

# 1. Remove the existing .git directory
echo "-> Removing old Git history..."
rm -rf .git

# 2. Initialize a new Git repository
echo "-> Initializing a new repository..."
git init

# 3. Add all files to the staging area
echo "-> Staging all files..."
git add .

# 4. Create the new initial commit
echo "-> Creating the initial commit..."
git commit -m "$COMMIT_MESSAGE"

# 5. Add the remote origin
echo "-> Adding remote origin..."
git remote add origin "$REMOTE_URL"

# 6. Rename the current branch to the desired name (e.g., main)
echo "-> Renaming branch to '$BRANCH_NAME'..."
git branch -M "$BRANCH_NAME"

# 7. Force push to the remote repository
echo "-> Force pushing to '$REMOTE_URL'..."
git push -u --force origin "$BRANCH_NAME"

echo "\nSuccess! Your repository has been flattened and pushed to GitHub."