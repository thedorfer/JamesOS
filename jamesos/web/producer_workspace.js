const optimizedProducerRender = baseProducerRender;
renderProducerProject = async id => {
  await optimizedProducerRender(id);
  const root = q("coloring-book-project");
  const project = await (await fetch(
    "/app/agency/coloring-book-producer/projects/" + encodeURIComponent(id),
    {cache: "no-store"},
  )).json();
  const samples = await (await fetch(
    "/app/agency/coloring-book-producer/projects/" + encodeURIComponent(id) + "/samples",
    {cache: "no-store"},
  )).json();
  const sections = [...root.querySelectorAll(":scope>section")];
  const sectionNames = {
    "Overview": "overview",
    "Book Brief": "brief",
    "Production Specification": "brief",
    "Page Plan": "plan",
    "Page Prompts": "prompts",
    "Sample Page Review": "samples",
    "Cover Brief": "cover",
    "Approvals": "approvals",
  };
  sections.forEach(section => {
    const key = sectionNames[section.querySelector(":scope>h5")?.textContent];
    if (key) section.dataset.workspaceTab = key;
  });

  root.querySelector(".producer-workspace-tabs")?.remove();
  const nav = document.createElement("nav");
  nav.className = "producer-workspace-tabs";
  nav.setAttribute("aria-label", "Project workspace");
  root.prepend(nav);
  const params = new URLSearchParams(location.search);
  const storageKey = "jamesos.producer.tab." + id;
  const allowed = ["overview", "brief", "plan", "prompts", "samples", "cover", "approvals"];
  let active = allowed.includes(params.get("producer_tab"))
    ? params.get("producer_tab")
    : allowed.includes(localStorage.getItem(storageKey))
      ? localStorage.getItem(storageKey)
      : "overview";
  const showTab = key => {
    active = key;
    localStorage.setItem(storageKey, key);
    params.set("project_id", id);
    params.set("producer_tab", key);
    history.replaceState(null, "", "/app?" + params.toString());
    sections.forEach(section => section.hidden = section.dataset.workspaceTab !== key);
    nav.querySelectorAll("button").forEach(
      button => button.setAttribute("aria-selected", String(button.dataset.tab === key)),
    );
  };
  [
    ["overview", "Overview"], ["brief", "Book Brief"], ["plan", "Page Plan"],
    ["prompts", "Page Prompts"], ["samples", "Sample Pages"], ["cover", "Cover"],
    ["approvals", "Approvals"],
  ].forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.tab = key;
    button.textContent = label;
    button.onclick = () => showTab(key);
    nav.append(button);
  });

  const plan = sections.find(section => section.dataset.workspaceTab === "plan");
  const pages = project.page_plan?.pages || [];
  if (plan && pages.length) {
    plan.querySelectorAll("article.agent-card").forEach(card => card.remove());
    const compact = document.createElement("div");
    compact.className = "page-plan-summary";
    compact.append(
      scoutText("Status", project.page_plan.status),
      scoutText("Page count", pages.length),
      scoutText("Revision", project.page_plan.plan_revision),
      scoutText("Validation", (project.page_plan.validation?.warnings || []).join(" · ") || "valid"),
      scoutText("Categories", JSON.stringify(project.page_plan.validation?.category_distribution || {})),
      scoutText("Characters", JSON.stringify(project.page_plan.validation?.character_distribution || {})),
    );
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search page ID or title";
    search.setAttribute("aria-label", "Search page plan");
    const table = document.createElement("table");
    table.className = "compact-page-table";
    const body = document.createElement("tbody");
    table.append(body);
    const pager = document.createElement("p");
    const editor = document.createElement("article");
    let offset = 0;
    let selected = 0;
    const drawEditor = () => {
      editor.replaceChildren();
      editor.className = "agent-card selected-page-editor";
      const page = pages[selected];
      const heading = document.createElement("strong");
      heading.textContent = "Edit " + page.page_id;
      editor.append(heading);
      ["title", "scene_summary", "setting", "main_action", "complexity"].forEach(key => {
        const field = producerField(key.replaceAll("_", " "), key, page[key]);
        field.querySelector("input").oninput = event => page[key] = event.target.value;
        editor.append(field);
      });
      const save = document.createElement("button");
      save.type = "button";
      save.textContent = "Save selected page";
      save.onclick = () => savePlan(id, pages);
      editor.append(save);
    };
    const draw = () => {
      body.replaceChildren();
      const term = search.value.toLowerCase();
      const matches = pages.map((page, index) => ({page, index})).filter(
        item => !term || item.page.page_id.toLowerCase().includes(term)
          || item.page.title.toLowerCase().includes(term),
      );
      matches.slice(offset, offset + 10).forEach(item => {
        const row = document.createElement("tr");
        const idCell = document.createElement("td");
        const pick = document.createElement("button");
        const title = document.createElement("td");
        pick.type = "button";
        pick.textContent = item.page.page_id;
        pick.onclick = () => { selected = item.index; drawEditor(); };
        idCell.append(pick);
        title.textContent = item.page.title;
        row.append(idCell, title);
        body.append(row);
      });
      pager.replaceChildren();
      const previous = document.createElement("button");
      const next = document.createElement("button");
      previous.type = next.type = "button";
      previous.textContent = "Previous";
      next.textContent = "Next";
      previous.disabled = offset === 0;
      next.disabled = offset + 10 >= matches.length;
      previous.onclick = () => { offset = Math.max(0, offset - 10); draw(); };
      next.onclick = () => { offset += 10; draw(); };
      pager.append(previous, ` ${offset + 1}–${Math.min(offset + 10, matches.length)} of ${matches.length} `, next);
    };
    search.oninput = () => { offset = 0; draw(); };
    plan.append(compact, search, table, pager, editor);
    draw();
    drawEditor();
  }

  const prompts = sections.find(section => section.dataset.workspaceTab === "prompts");
  if (prompts) {
    prompts.replaceChildren(prompts.querySelector("h5"));
    (project.page_prompts?.prompts || []).forEach(prompt => {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${prompt.prompt_id} · ${prompt.page_id}`;
      details.append(summary);
      details.ontoggle = () => {
        if (details.open && details.children.length === 1) {
          details.append(scoutText("Prompt", `${prompt.positive_prompt} Avoid: ${prompt.negative_prompt}`));
        }
      };
      prompts.append(details);
    });
  }

  let review = sections.find(
    section => section.querySelector(":scope>h5")?.textContent === "Sample Page Review",
  );
  if (!review) {
    review = document.createElement("section");
    review.dataset.workspaceTab = "samples";
    const heading = document.createElement("h5");
    heading.textContent = "Sample Page Review";
    review.append(heading);
    (samples.artifacts || []).forEach(item => {
      const card = document.createElement("article");
      const title = document.createElement("strong");
      const image = document.createElement("img");
      card.className = "agent-card";
      card.dataset.pageId = item.page_id;
      card.dataset.assetId = item.asset_id;
      title.textContent = `${item.page_id} · ${item.review_state}`;
      image.src = `/app/agency/coloring-book-producer/projects/${encodeURIComponent(id)}/samples/${encodeURIComponent(item.asset_id)}`;
      image.alt = `Candidate ${item.asset_id}`;
      image.style.maxWidth = "min(100%, 520px)";
      card.append(
        title,
        image,
        scoutText("Profile", item.profile_id),
        scoutText("Prompt revision", item.prompt_revision),
      );
      const technical = document.createElement("details");
      const technicalSummary = document.createElement("summary");
      technicalSummary.textContent = "Technical details";
      technical.append(technicalSummary);
      technical.ontoggle = () => {
        if (technical.open && technical.children.length === 1) {
          const pre = document.createElement("pre");
          pre.textContent = JSON.stringify(item.technical_validation || {}, null, 2);
          technical.append(pre);
        }
      };
      card.append(technical);
      [["Approve", "approve"], ["Reject", "reject"]].forEach(([label, action]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = label;
        button.onclick = () => reviewSample(id, item.asset_id, action);
        card.append(button);
      });
      const edit = document.createElement("button");
      const form = document.createElement("div");
      const positive = document.createElement("textarea");
      const negative = document.createElement("textarea");
      const save = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Edit Prompt";
      form.hidden = true;
      positive.value = item.prompt_details?.positive_prompt || "";
      negative.value = item.prompt_details?.negative_prompt || "";
      save.type = "button";
      save.textContent = "Save Prompt Override Locally";
      save.onclick = () => saveSamplePrompt(id, item.page_id, positive.value, negative.value, save);
      edit.onclick = () => form.hidden = !form.hidden;
      form.append("Positive prompt", positive, "Negative prompt", negative, save);
      card.append(edit, form);
      const regenerate = document.createElement("button");
      regenerate.type = "button";
      regenerate.textContent = "Regenerate page-001 with updated prompt";
      regenerate.onclick = () => regenerateUpdatedPrompt(
        id, item.asset_id, regenerate, "kids-bold-line-art-v6",
      );
      card.append(regenerate);
      const reference = document.createElement("button");
      reference.type = "button";
      reference.textContent = item.reference_candidate
        ? "Reference Candidate"
        : "Mark as Reference Candidate";
      reference.disabled = !!item.reference_candidate;
      reference.onclick = async () => {
        const response = await samplePost(
          `/app/agency/coloring-book-producer/projects/${encodeURIComponent(id)}/samples/${encodeURIComponent(item.asset_id)}/reference`,
          {},
        );
        const value = await sampleResponseJson(response);
        q("coloring-book-status").textContent = response.ok
          ? "Reference candidate saved locally. This is not an approval."
          : value.detail || "Reference candidate was not saved.";
        if (response.ok) renderProducerProject(id);
      };
      card.append(reference);
      review.append(card);
    });
    if (!(samples.artifacts || []).length && samples.project_status === "page_plan_approved") {
      const generate = document.createElement("button");
      generate.type = "button";
      generate.textContent = "Generate 3 Sample Pages";
      generate.onclick = () => generateSamples(id, generate);
      review.append(generate);
    }
    root.append(review);
    sections.push(review);
  }
  if (review) {
    const progress = samples.progress || {};
    const progressPanel = document.createElement("aside");
    progressPanel.className = "sample-generation-status";
    progressPanel.dataset.operationState = progress.operation_state || samples.operation_state || samples.status;
    const progressLabel = progress.operation_state === "provider_submitted"
      ? "Submitted to ComfyUI…"
      : progress.operation_state === "running"
        ? "Generating locally…"
        : progress.operation_state === "failed"
          ? "Failed safely"
          : progress.operation_state === "retry_authorized"
            ? "Retry authorization required"
            : "Ready for review";
    progressPanel.append(
      scoutText("Sample Generation Status", progressLabel),
      scoutText("Operation", progress.operation_type || "none"),
      scoutText("Pages", (progress.page_ids || []).join(", ") || "none"),
      scoutText("ComfyUI prompts", (progress.submitted_prompt_ids || []).join(", ") || "none"),
      scoutText("Failure", progress.safe_failure_message || samples.safe_failure_message || "none"),
    );
    const refreshStatus = document.createElement("button");
    refreshStatus.type = "button";
    refreshStatus.textContent = "Refresh Status";
    refreshStatus.onclick = () => renderProducerProject(id);
    progressPanel.append(refreshStatus);
    review.prepend(progressPanel);
    if (samples.operation_state === "retry_authorized") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Retry Unfinished Sample Page";
      retry.onclick = () => retryUnfinishedSamples(id, retry);
      review.append(
        scoutText(
          "Retry pages",
          (samples.retry_pages || []).map(page => `${page.page_id} — ${page.title}`).join(", "),
        ),
        retry,
      );
    } else if (samples.operation_state === "remaining_samples_authorized") {
      const remaining = document.createElement("button");
      remaining.type = "button";
      remaining.textContent = "Generate Remaining Sample Pages";
      remaining.onclick = () => retryUnfinishedSamples(id, remaining);
      review.append(remaining);
    }
    const allCards = [...review.querySelectorAll("article.agent-card")];
    allCards.forEach((card, index) => {
      const item = (samples.artifacts || [])[index];
      if (item) {
        card.dataset.pageId = item.page_id;
        card.dataset.assetId = item.asset_id;
      }
    });
    const cards = allCards.filter(card => card.dataset.pageId === "page-001");
    const items = (samples.artifacts || []).filter(item => item.page_id === "page-001");
    const newest = items.at(-1);
    const reference = items.find(item => item.reference_candidate);
    const activeCard = cards.find(card => card.dataset.assetId === newest?.asset_id);
    const referenceCard = cards.find(card => card.dataset.assetId === reference?.asset_id);
    cards.forEach(card => {
      card.querySelectorAll("pre").forEach(pre => pre.remove());
      const item = items.find(value => value.asset_id === card.dataset.assetId);
      const image = card.querySelector("img");
      if (card === activeCard) {
        card.classList.add("active-sample-candidate", "newest-candidate-highlight");
        card.prepend(scoutText("Candidate", "Latest candidate"));
        if (!item?.technical_validation?.valid) {
          const approve = [...card.querySelectorAll("button")].find(button => button.textContent === "Approve");
          if (approve) {
            approve.disabled = true;
            approve.title = "Technical validation must pass before approval.";
          }
        }
      } else {
        card.querySelectorAll("button").forEach(button => {
          if (!["Mark as Reference Candidate", "Reference Candidate"].includes(button.textContent)) button.remove();
        });
        if (image) image.loading = "lazy";
      }
    });
    if (referenceCard && referenceCard !== activeCard) {
      referenceCard.classList.add("reference-sample-candidate");
      referenceCard.prepend(scoutText("Candidate", "Reference candidate"));
    } else if (reference && referenceCard === activeCard) {
      const compactReference = document.createElement("article");
      const image = document.createElement("img");
      compactReference.className = "reference-sample-candidate";
      image.src = `/app/agency/coloring-book-producer/projects/${encodeURIComponent(id)}/samples/${encodeURIComponent(reference.asset_id)}`;
      image.alt = `Reference candidate ${reference.asset_id}`;
      image.loading = "lazy";
      image.style.maxWidth = "140px";
      compactReference.append(
        scoutText("Candidate", "Reference candidate"),
        image,
        scoutText("Profile", reference.profile_id),
        scoutText("Prompt revision", reference.prompt_revision),
        scoutText("State", "Local reference — not approval"),
      );
      review.append(compactReference);
    }
    const historical = cards.filter(card => card !== activeCard && card !== referenceCard);
    const historyDetails = document.createElement("details");
    const historySummary = document.createElement("summary");
    const grid = document.createElement("div");
    historyDetails.className = "sample-candidate-history";
    historySummary.textContent = `Candidate history (${historical.length})`;
    grid.className = "candidate-thumbnail-grid";
    historical.forEach(card => {
      card.classList.add("historical-sample-candidate");
      card.prepend(scoutText("Candidate", "Historical candidate"));
      grid.append(card);
    });
    historyDetails.append(historySummary, grid);
    review.append(historyDetails);
    const policy = samples.page_generation_policy || {};
    if (activeCard) {
      const status = document.createElement("div");
      status.className = "attempt-summary";
      const generation = policy.generation_state === "generation_available"
        ? "Generation available"
        : policy.generation_state === "exact_attempt_already_used"
          ? "Exact attempt already used"
          : "Maximum attempts reached";
      status.append(
        scoutText("Attempts", `${policy.attempts_used || 0} of ${policy.maximum_attempts_per_page || 3}`),
        scoutText("Current prompt revision", policy.current_prompt_revision ?? "unknown"),
        scoutText("Latest generated revision", policy.latest_generated_revision ?? "unknown"),
        scoutText("Generation", generation),
      );
      activeCard.prepend(status);
      const regenerate = [...activeCard.querySelectorAll("button")].find(
        button => button.textContent === "Regenerate page-001 with updated prompt",
      );
      if (regenerate) {
        regenerate.disabled = !!samples.progress?.active || policy.generation_available === false;
        regenerate.onclick = () => regenerateUpdatedPrompt(
          id, newest.asset_id, regenerate, "kids-bold-line-art-v6",
        );
      }
    }
    if (
      samples.progress?.operation_type === "regenerate_single_page"
      && samples.progress.operation_state === "review_ready"
      && newest?.generation_attempt_identity === samples.progress.generation_attempt_identity
      && Number(newest?.prompt_revision) === Number(samples.progress.prompt_revision)
      && newest?.positive_prompt_hash === samples.progress.positive_prompt_hash
      && newest?.negative_prompt_hash === samples.progress.negative_prompt_hash
      && activeCard
    ) {
      const notice = document.createElement("p");
      notice.textContent = "New page-001 candidate ready for review.";
      notice.setAttribute("role", "status");
      review.prepend(notice);
      if (active === "samples") activeCard.scrollIntoView({block: "center"});
    }
    if (samples.progress?.active) {
      review.querySelectorAll("button").forEach(button => {
        if (/Generate|Regenerate/.test(button.textContent)) button.disabled = true;
      });
      clearTimeout(window.__producerSamplePoll);
      window.__producerSamplePoll = setTimeout(() => renderProducerProject(id), 3000);
    }
  }
  showTab(active);
};
