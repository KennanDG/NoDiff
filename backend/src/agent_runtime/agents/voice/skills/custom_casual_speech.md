# Skill: Casual Speech 

Purpose: Help the voice agent turn a conversational intent into short, natural, casual spoken phrasing, using the casual_phrase tool for wording (plus alternatives) while keeping replies brief, clear, and appropriate to the user's tone.

Use when:
- The user wants a casual, chatty, or friendly way to say something.
- The agent needs a short spoken acknowledgement, greeting, or sign-off.
- The user asks for alternative phrasings of a casual line.
- A reply risks sounding stiff, formal, or overly long for voice.
- The agent is unsure which casual wording fits the conversational intent.

Allowed tools:
- casual_phrase

Steps:
1. Identify the conversational intent from the user's request (e.g., greeting, agreement, apology, encouragement, sign-off).
2. Note any tone or audience constraint the user gave (friendly, low-key, upbeat, brief).
3. Call casual_phrase with that intent to get a short phrase plus alternatives.
4. Select the single phrase that best fits the user's tone and the voice context.
5. Say the selected phrase as the answer, keeping it short enough to speak in one breath.
6. If the user asked for options, list the alternatives concisely, one per line or comma-separated.
7. If the tool returns nothing usable, fall back to a plain, neutral short phrase and say it is a fallback.

Rules:
- Only use the casual_phrase tool; do not reach for filesystem or search tools for wording tasks.
- Keep every spoken line short — casual speech for voice should be one or two sentences at most.
- Match the user's requested tone; do not add slang, humor, or familiarity they did not ask for.
- Never use casual phrasing for factual, technical, legal, medical, or safety-critical answers.
- Do not invent tool capabilities or claim a phrase came from the tool if it did not.
- If the tool fails or returns nothing, say so and offer a simple neutral alternative instead of fabricating.
- Avoid repeating the same casual phrase back-to-back in a conversation; vary wording when alternatives are available.
- Do not store, log, or persist anything about the user's conversation.
