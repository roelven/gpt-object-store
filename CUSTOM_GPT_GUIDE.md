# Building a Custom GPT with GPT Object Store

This guide walks you through creating a Custom GPT that uses the GPT Object Store as its backend for persistent data storage. We'll build a **Daily Diary GPT** as an example - a personal journaling assistant that stores daily entries and provides weekly summaries.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setting Up Your GPT Object Store](#setting-up-your-gpt-object-store)
3. [Creating Your Custom GPT](#creating-your-custom-gpt)
4. [Configuring GPT Actions](#configuring-gpt-actions)
5. [Writing GPT Instructions](#writing-gpt-instructions)
6. [Testing Your Diary GPT](#testing-your-diary-gpt)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

Before starting, you'll need:

- **ChatGPT Plus or Team subscription** (required for Custom GPTs)
- **GPT Object Store deployed** with a public HTTPS endpoint
- **API key** for authentication
- **Basic understanding** of REST APIs and JSON

## Setting Up Your GPT Object Store

### 1. Deploy the GPT Object Store

First, ensure your GPT Object Store is deployed and accessible via HTTPS:

```bash
# Clone and deploy the GPT Object Store
git clone https://github.com/yourusername/gpt-object-store.git
cd gpt-object-store

# Configure your environment
cd ops
cp .env.sample .env
# Edit .env with your configuration
vim .env  # Set API_URL, database credentials, etc.

# Start services
docker compose up -d
```

### 2. Create a GPT and API Key

Create a GPT identity and generate an API key using the provided Makefile commands:

```bash
cd ops

# Create a GPT for the diary
make create-gpt ID=diary-gpt NAME="Daily Diary Assistant"

# Generate an API key (save this - you'll need it later)
make create-key GPT_ID=diary-gpt
# Output: API Key: <your-generated-key>
# ⚠️ Save this key securely - it cannot be retrieved again!

# Verify the GPT was created
make list-gpts

# Check API keys for your GPT
make list-keys GPT_ID=diary-gpt
```

**Note**: The API key will only be shown once when created. Store it securely as it cannot be retrieved later.

### 3. Create a Collection

Create a collection to store diary entries:

```bash
curl -X POST https://api.yourdomain.com/v1/gpts/diary-gpt/collections \
  -H "Authorization: Bearer your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "diary_entries",
    "schema": {
      "type": "object",
      "properties": {
        "date": {"type": "string", "format": "date"},
        "entry": {"type": "string"},
        "mood": {"type": "string", "enum": ["happy", "sad", "neutral", "excited", "anxious"]},
        "tags": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["date", "entry"]
    }
  }'
```

**Expected Response:**
```json
{
  "name": "diary_entries",
  "schema": {
    "type": "object",
    "properties": {
      "date": {"type": "string", "format": "date"},
      "entry": {"type": "string"},
      "mood": {"type": "string", "enum": ["happy", "sad", "neutral", "excited", "anxious"]},
      "tags": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["date", "entry"]
  },
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "gpt_id": "diary-gpt",
  "created_at": "2024-01-01T12:00:00Z"
}
```

## Creating Your Custom GPT

### 1. Navigate to GPT Builder

1. Go to [ChatGPT](https://chat.openai.com)
2. Click on your profile → "My GPTs"
3. Click "Create a GPT"

### 2. Configure Basic Settings

In the **Configure** tab, set:

- **Name**: Daily Diary Assistant
- **Description**: Your personal journaling companion that remembers your daily thoughts and provides weekly reflections
- **Instructions**: (See detailed instructions below)

### 3. Upload Profile Picture

Create or generate an appropriate icon for your diary GPT (optional but recommended).

## Configuring GPT Actions

This is the most important step - configuring your GPT to communicate with the Object Store.

### 1. Add Actions

In the GPT Builder, go to the **Configure** tab and scroll to **Actions**:

1. Click "Create new action"
2. Click "Import from URL" 
3. Enter: `https://api.yourdomain.com/openapi.json`
4. Click "Import" to load the schema

**Note**: The OpenAPI schema is automatically maintained and always reflects the current API capabilities. This method ensures you always have the most up-to-date schema with all available operations and the latest features.

### 2. Configure Authentication

1. In the **Authentication** section, select "API Key"
2. Set **Auth Type** to "Bearer"
3. Enter your API key: `your-secret-api-key-here`

### 3. Test the Connection

Click "Test" to verify the GPT can connect to your API. You should see a successful response.

## Writing GPT Instructions

Add these comprehensive instructions to your GPT:

```markdown
You are a Daily Diary Assistant, a thoughtful and empathetic journaling companion. Your role is to help users capture their daily thoughts, feelings, and experiences, and provide meaningful weekly reflections.

## Core Capabilities

You have access to a persistent storage backend where you can:
- Save daily diary entries with date, content, mood, and tags
- Retrieve past entries for review and reflection
- Update or delete entries as needed
- Generate weekly summaries and insights

## Interaction Guidelines

### When a user wants to make a diary entry:

1. **Warmly greet them** and ask about their day
2. **Listen actively** to what they share
3. **Ask follow-up questions** to help them explore their thoughts:
   - "How did that make you feel?"
   - "What was the highlight of your day?"
   - "What challenged you today?"
4. **Identify their mood** from the conversation (happy, sad, neutral, excited, anxious)
5. **Extract relevant tags** from their entry (work, family, health, goals, etc.)
6. **Save the entry** using the saveDiaryEntry action with today's date

### When a user requests a weekly summary:

1. **Retrieve the last 7 days** of entries using getDiaryEntries with limit=7
2. **Analyze the entries** for:
   - Recurring themes or patterns
   - Mood trends
   - Accomplishments and challenges
   - Growth opportunities
3. **Present a thoughtful summary** that includes:
   - Overall mood for the week
   - Key highlights and achievements
   - Patterns you've noticed
   - Gentle insights or suggestions
   - Encouragement for the week ahead

### When a user wants to review past entries:

1. **Ask for the time period** they want to review
2. **Retrieve the relevant entries** using getDiaryEntries
3. **Present them in a readable format** with dates and key points
4. **Offer to help them reflect** on patterns or growth

### When a user wants to edit or delete an entry:

1. **Help them find the specific entry** by date or content
2. **Confirm the changes** they want to make
3. **Use updateDiaryEntry or deleteDiaryEntry** as appropriate
4. **Acknowledge the change** and offer support

## Important Behaviors

- **Privacy First**: Never share or reference diary entries outside the current conversation
- **Empathetic Tone**: Always be supportive, non-judgmental, and encouraging
- **Active Listening**: Show that you're engaged by referencing specific details they've shared
- **Gentle Prompting**: If someone hasn't journaled in a while, gently encourage them
- **Respect Boundaries**: If someone doesn't want to share certain details, respect that
- **Date Awareness**: Always use the current date for new entries unless specified otherwise

## Data Structure

When saving entries, use this format:
```json
{
  "body": {
    "date": "YYYY-MM-DD",
    "entry": "The full diary entry text",
    "mood": "one of: happy, sad, neutral, excited, anxious",
    "tags": ["relevant", "tags", "from", "conversation"]
  }
}
```

## Example Interactions

**User**: "I had a really tough day at work today"
**You**: "I'm sorry to hear you had a tough day. Would you like to tell me what happened? Sometimes sharing can help lighten the load."

**User**: "Can you show me my entries from this week?"
**You**: "Of course! Let me retrieve your entries from the past week and we can reflect on them together..."

**User**: "Give me a summary of how I've been doing"
**You**: "I'll create a thoughtful summary of your recent entries. Let me look at your past week..."

Remember: You're not just storing data - you're helping someone process their life experiences and grow through reflection.
```

## Testing Your Diary GPT

### Test Scenario 1: Creating an Entry

**You**: "I want to journal about my day"

**Expected GPT Response**: The GPT should engage you in conversation about your day, then save an entry.

**Verify**: Check that the entry was saved:
```bash
curl -X GET https://api.yourdomain.com/v1/gpts/diary-gpt/collections/diary_entries/objects \
  -H "Authorization: Bearer your-secret-api-key-here"
```

### Test Scenario 2: Weekly Summary

**You**: "Can you give me a summary of my week?"

**Expected GPT Response**: The GPT should retrieve your recent entries and provide a thoughtful analysis.

### Test Scenario 3: Reviewing Past Entries

**You**: "Show me what I wrote last Monday"

**Expected GPT Response**: The GPT should retrieve and display the specific entry.

## Advanced Features

### 1. Mood Tracking Visualization

Extend your GPT to track mood patterns:

```python
# GPT can suggest mood trends
"Over the past week, I noticed your mood has been:
- Happy: 3 days
- Neutral: 2 days  
- Anxious: 2 days

You tend to feel happiest on weekends and after exercise."
```

### 2. Goal Tracking

Add goal tracking to entries:

```json
{
  "body": {
    "date": "2024-01-15",
    "entry": "Worked on my fitness goals today...",
    "mood": "excited",
    "tags": ["fitness", "goals"],
    "goals": {
      "fitness": "Ran 3 miles",
      "reading": "Read 20 pages"
    }
  }
}
```

### 3. Prompts and Templates

Create guided journaling prompts:

- Gratitude journaling: "What are three things you're grateful for today?"
- Growth reflection: "What did you learn about yourself this week?"
- Future planning: "What are your intentions for tomorrow?"

### 4. Export Functionality

While the GPT can't directly create files, it can format entries for copying:

```markdown
## Your Diary Entries - January 2024

### January 15, 2024
**Mood**: Happy
**Tags**: work, achievement

Today was fantastic! I finally completed the project...

---

### January 14, 2024
**Mood**: Neutral
**Tags**: weekend, family

Quiet Saturday with the family...
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Authentication Errors (401)

**Problem**: "The GPT says it can't authenticate"

**Solution**: 
- Verify your API key is correct
- Check that the Bearer token is properly configured
- Ensure the API key hasn't been revoked

#### 2. Connection Timeouts

**Problem**: "The GPT times out when trying to save"

**Solution**:
- Check your API server is running and accessible
- Verify HTTPS certificate is valid
- Test the endpoint directly with curl

#### 3. Data Not Persisting

**Problem**: "Entries aren't being saved"

**Solution**:
- Check the GPT is calling the correct endpoints
- Verify the collection exists
- Check database connectivity

#### 4. Rate Limiting (429)

**Problem**: "Getting rate limit errors"

**Solution**:
- Default limits are 60 requests/minute
- Implement pagination for large retrievals
- Consider increasing limits in your deployment

### Debugging Tips

1. **Enable Debug Mode**: Ask the GPT to show you the exact API calls it's making
2. **Check Logs**: Review your API server logs for errors
3. **Test Manually**: Use curl to test the same operations
4. **Verify Schema**: Ensure your OpenAPI schema matches your API

## Best Practices

### 1. Data Privacy

- Use encryption for sensitive diary content
- Implement proper access controls
- Regular backups of user data
- Clear data retention policies

### 2. User Experience

- Keep responses conversational and natural
- Don't make users aware of technical operations
- Handle errors gracefully with helpful messages
- Provide value beyond just storage (insights, patterns, encouragement)

### 3. Performance

- Use pagination for retrieving multiple entries
- Cache frequently accessed data
- Optimize queries for common patterns
- Monitor API response times

### 4. Maintenance

- Regular testing of all operations
- Monitor error rates and user feedback
- Update GPT instructions based on usage patterns
- Keep API documentation synchronized

## Extending Your Diary GPT

### Integration Ideas

1. **Calendar Integration**: Link entries to calendar events
2. **Weather Context**: Add weather data to entries automatically
3. **Photo Memories**: Reference photo URLs in entries
4. **Health Tracking**: Integrate mood with sleep, exercise data
5. **Writing Analytics**: Track writing patterns and vocabulary

### Multi-User Considerations

If sharing the GPT with others:

1. Each user needs their own API key
2. Consider implementing user scoping in your backend
3. Add privacy disclaimers to GPT instructions
4. Implement proper data isolation

## Conclusion

You now have a fully functional Daily Diary GPT that:
- ✅ Stores entries persistently in your GPT Object Store
- ✅ Retrieves and analyzes past entries
- ✅ Provides meaningful weekly summaries
- ✅ Helps users reflect on their experiences
- ✅ Maintains privacy and security

This same pattern can be applied to create any Custom GPT that needs persistent storage:
- **Habit Tracker GPT**: Track daily habits and progress
- **Learning Journal GPT**: Document learning journey and insights
- **Project Manager GPT**: Store project tasks and updates
- **Recipe Collection GPT**: Save and organize favorite recipes
- **Workout Logger GPT**: Track exercise routines and progress

The GPT Object Store provides the flexible backend you need to build powerful, stateful Custom GPTs that remember and learn from every interaction.

## Resources

- [GPT Object Store Documentation](README.md)
- [OpenAI Custom GPT Documentation](https://help.openai.com/en/articles/8770868-gpt-builder)
- [API Reference](https://api.yourdomain.com/docs)
- [Support and Issues](https://github.com/yourusername/gpt-object-store/issues)

---

*Happy journaling! 📔✨*