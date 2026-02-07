#!/bin/bash
# Verification script to check if prompt files are included in Docker image

echo "🔍 Verifying deployment files..."
echo ""

# Check if prompts directory exists
if [ -d "prompts" ]; then
    echo "✅ prompts/ directory exists"
    
    # Check for report prompts
    if [ -d "prompts/report" ]; then
        echo "✅ prompts/report/ directory exists"
        echo "   Files in prompts/report/:"
        ls -la prompts/report/ | grep -E "\.txt$" || echo "   ⚠️  No .txt files found!"
    else
        echo "❌ prompts/report/ directory NOT found!"
    fi
    
    # Check for followup prompts
    if [ -d "prompts/followup" ]; then
        echo "✅ prompts/followup/ directory exists"
        echo "   Files in prompts/followup/:"
        ls -la prompts/followup/ | grep -E "\.txt$" || echo "   ⚠️  No .txt files found!"
    else
        echo "❌ prompts/followup/ directory NOT found!"
    fi
else
    echo "❌ prompts/ directory NOT found!"
fi

echo ""
echo "📋 Checking .dockerignore..."
if [ -f ".dockerignore" ]; then
    echo "   Contents:"
    cat .dockerignore
    if grep -q "prompts" .dockerignore; then
        echo "   ⚠️  WARNING: 'prompts' is in .dockerignore - this will exclude prompt files!"
    else
        echo "   ✅ 'prompts' is NOT excluded in .dockerignore"
    fi
else
    echo "   ✅ No .dockerignore file (all files will be included)"
fi

echo ""
echo "✅ Verification complete!"







