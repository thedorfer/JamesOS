# JamesOS Architecture

JamesOS is an approval-first personal operating system. It keeps human notes separate from machine-owned data, turns local evidence into structured context, and uses Jade as the conversational layer over that context.

## Evidence To Reasoning

Local evidence flows through these layers:

- Evidence sources: notes, email archives, calendar imports, reports, timelines, attachments, ChatGPT imports, and phone logs.
- Knowledge Graph and Working Memory: local entities such as people, projects, tickets, files, and decisions are normalized into searchable memory.
- Reasoner: Jade chooses context from the Knowledge Graph, Working Memory, reports, and tools before answering.
- UI: Jade presents concise answers, evidence labels, and clickable local knowledge items when available.

The rule is simple: generated answers and automations should be grounded in local evidence whenever they claim to know something.

## Job Queue

The Job Queue is the automation backbone. It stores durable JSON jobs under:

- `~/JamesOSData/JamesOS/Queue/pending`
- `~/JamesOSData/JamesOS/Queue/in_progress`
- `~/JamesOSData/JamesOS/Queue/processed`
- `~/JamesOSData/JamesOS/Queue/failed`

Each job records its id, type, status, timestamps, priority, approval state, payload, steps, and logs. Approval-gated jobs cannot complete until approved.

Phase 1 only creates the queue and API/script controls. It does not run autonomous publishing, ordering, sending, or creative generation.

## Jade Creative Studio

Jade Creative Studio is planned as the creative automation surface for products, images, copy, and review workflows. It will sit on top of the Job Queue so every meaningful action can be inspected, approved, retried, or failed safely.

## UnityStitches

UnityStitches daily product generation will become a draft-only pipeline for inclusive Etsy/Printify products. Future phases may create product draft packages with titles, descriptions, tags, prompts, artwork paths, blueprint notes, and review status.

No UnityStitches product is published, ordered, sent to production, or listed live without James approval.

## ComfyUI

ComfyUI is the planned local image engine. JamesOS owns the workflow and approval model; ComfyUI only renders images from approved local prompts/workflows.

Phase 1 does not call ComfyUI or generate images.

## Printify And Etsy

Printify is the future publishing target for product drafts. Etsy is the future sales platform. Both integrations must remain draft-only until James explicitly approves publication.

Phase 1 does not call Printify, Etsy, order products, send products to production, or create live listings.

## Sales Intelligence

Future sales intelligence can analyze drafts, shops, seasonal timing, niches, performance, and pricing. It should remain advisory unless a specific approved job authorizes an action.

## Safety Model

- Approval-first automation.
- Draft-only creative and product workflows by default.
- No approval-gated job can complete unless approved.
- No publishing, ordering, sending, live Etsy listing, or Printify production action without James approval.
- Machine-owned data stays under `~/JamesOSData`.
