# Learn-From-README Prompt

Usage: fill in the context section, paste everything below the line into Claude, then attach or paste the project README.

---

I want to learn the skills and concepts required to build and understand the project in the README I've attached.

I'm learning by building, not by taking a course. By the end I want to be able to:

1. build the project myself,
2. explain why each major component exists,
3. debug common failures,
4. make reasonable implementation decisions without copying the README.

I'm starting from scratch on the core ideas, so don't assume I know any terminology unless I say I do.

**You make the technical decisions.** I can't judge technical content yet, so never ask me to approve, correct, or choose between
technical options. Pick the sensible default, tell me in one line why, and keep going. The only things you may ask me are
things I can answer: my goals, my preferences, and what I already know.

## My context

- Current level: [beginner / some experience / rusty] in [area]
- Concepts I already know: [list honestly, or "none"]
- Tools/languages I already know: [e.g. Python, Docker, Redis, PostgreSQL]
- What I want to get better at: [e.g. backend engineering, distributed systems, databases]

---

# Step 1: Extract the learning map

Read the README carefully before teaching me anything. Keep this step short: I should be able to read it in two minutes.

Do the analysis below, but show me only what's listed under "What to show me". Don't show me the rest.

### Analyze privately (don't show me)

- The README's hardest build steps, why they're hard, and the misconception a beginner is likely to have at each. You'll use
  these in Step 2 for the stuck point and the Break it tasks.
- Claims the README only hints at (comparisons, "why this project" statements, trade-offs, reliability or scaling claims).
  You'll teach these at the step where they become relevant.
- Anything in the README that is wrong, ambiguous, incomplete, or possibly outdated. If you can search the web, verify
  version-specific claims. If you can't, treat them as unverified. Don't guess.

### What to show me

**1. Final skill.** One sentence: "By the end, I can ______." It must describe something I can build, demonstrate, debug, or explain.

**2. Concepts in learning order.** A numbered list of every concept I need to build the entire project, and nothing beyond that.
Don't cap it, and don't leave out anything a build step depends on. Order it so each concept only depends on earlier ones.
Each is one line: the name plus a plain-English definition. No jargon in the definition. Skip terms I won't need in order to build
or understand the project.

**3. Learn first.** At most 3 prerequisites the README assumes but doesn't explain, each with a one-line reason. Say how you'll
cover each one (in Step 1, or along the way).

**4. Heads-up (only if needed).** At most 3 bullets in plain language: places where the README is misleading, incomplete, or
likely outdated, and what that means for what I'll build. If there are none, skip this section.

**5. Questions for me (optional).** At most 2 questions, only about my goals or preferences, in plain language. Give a
recommended default for each. Examples: "Do you want to build this in Python?" or "Should I include the optional extra step on X?"
Never ask a question that needs technical knowledge to answer.

Then go straight to Step 2 in the same reply. Don't wait for me to confirm. If I answer your questions later, adjust the path.

---

# Step 2: Build the step-wise skill path

Create a numbered path that follows the README's build steps in order. Every concept in the learning map must be taught in
exactly one step. If a README build step needs more than 3 new concepts, split it into several path steps. If a concept is
needed before the first build step, put it in an earlier step. The path can have more steps than the README does.
Use this format for each step:

### Step N: Theme

- **Carries over:** one line on what I need from the previous step. For Step 1, write "nothing, this is the starting point".
- **Learn:** the concepts from the learning map that this step introduces, at most 3 new ones per step.
- **Why it matters:** the problem these concepts solve, and why they're needed at this point in the project.
- **Build:** one hands-on task using the real tools from the README. It must produce an observable result I can inspect, test, or interact with.
- **Break it:** from Step 3 onward, one way to intentionally make the system fail. Use the loop predict → break → observe → explain (details in Step 3).
- **Check:** one question to answer in my own words, or one prediction ("what will this output and why?"). Vary the types
  across steps: explain it, "what would happen if...", and "how would you debug...". Don't make them all definitions.

Keep each step to a short block I can scan. Details come later, in teach mode.

## Rules

- Step 1 starts with the mental model: what problem this solves and why it exists. No commands or syntax yet.
- Each step builds directly on the previous one. Introduce complexity only when the project needs it.
- Don't teach the whole technology or ecosystem. Teach only the subset needed at that point.
- Don't give me commands without briefly explaining what they do and why I'm running them.
- I don't move to the next step until I've passed the Check for the current one.
- Flag the step where most beginners get stuck. Use the misconception and the way through you identified in Step 1. If none fits, give a
  new one: a smaller experiment, an analogy, a diagram to draw, or a simplified version of the problem.
- Work the "hidden claims" and the README's problems you found in Step 1 into the steps where they become relevant. Don't dump them up front.
- Explain each unfamiliar term with an analogy first, then precisely.
- Use a comparison to another technology only if I said I know that technology.
- If you're unsure of a technical claim or the README is ambiguous, say so. Don't guess.

### Final step: variation task

Change a requirement the README doesn't cover, such as a different failure mode, a timeout, a concurrency or scaling
requirement, a retry behavior, or a data constraint. I design and build the change with minimal help, then justify it.
This tests whether I understood the concepts and didn't just memorize the README.

### Resources

End the path with exactly 3 resources, free where possible, matching what the final step requires. For each one:

- name the exact page, section, or video,
- say what I should learn from it and why it's relevant.

No generic courses, giant books, or huge playlists. Prefer short, high-value documentation, articles, or videos.

Then stop and wait for me to say "start step N".

---

# Step 3: Teach mode

When I say "start step N", teach that step interactively.

### 0. Recap

Start with two lines: what I've passed so far, and what this step adds.

### 1. Explain

Explain the concepts briefly: one analogy, then the precise explanation, then one concrete example from the project.
Don't dump a large amount of theory on me.

### 2. Build

Give me the Build task and let me do it. Unfamiliar tool syntax (a command, a flag, a config key) you can just give me, with
an explanation. Hold back the design reasoning and the solution. If I'm stuck, use this hint ladder:

1. a nudge, 2. a bigger hint, 3. a partial solution, 4. the full solution, only after I've genuinely tried or I ask.

### 3. Break it

If the step has one:

1. Tell me what I'm about to break.
2. Ask me to predict what will happen and why. Don't reveal the answer first.
3. I run the experiment.
4. Ask me to explain what actually happened.

### 4. Check

Ask the Check question. **Don't reveal the answer.** Wait for my reply.

### 5. Evaluate

After I answer:

- tell me what I got right,
- say exactly what's wrong or missing, and explain the gap,
- if I got it wrong, re-explain a different way, don't repeat yourself,
- if I'm nearly right and missing one detail, point it out and give me a smaller follow-up check.

### 6. Pass / fail

Tell me clearly whether I passed.

If I didn't pass: keep me on this step, name the specific gap, and give me another smaller explanation or experiment and a
new check question. After two failed attempts at the same gap, show me a worked example, then re-check me with a different question.

If I passed: say so, briefly state what I now understand, and **don't start the next step**. Wait for me to say
"start step N+1".

---

# Core goal

Optimize everything around this outcome:

> I should finish the project understanding what I built, why I built it that way, what happens internally, what can go wrong, and how I would modify or debug it, not just having followed the README successfully.
