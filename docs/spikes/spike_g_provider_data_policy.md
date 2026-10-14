# Spike G · Provider Data Policy

- **Status:** Complete (desk research, 2026-10-13). O4 still needs PARI's answer.
- **Started:** 2026-10-13
- **Owner:** Binjie Wang
- **Related:** R10 · A5 · O4 (see [`risk_register.md`](../risk_register.md)); [`01_discovery.md`](../01_discovery.md) §10
- **Throwaway code:** none (desk research)
- **Budget:** $0

---

## Outcome

- **Neither provider trains on our API data.** OpenAI keeps inputs and outputs in abuse-monitoring logs for up to
  **30 days** unless we are approved for Zero Data Retention. Alibaba stores request data **in the region we
  call** (US, Virginia) but does not publish a retention period.
- **Our Qwen setup sits on a path Alibaba no longer documents for the US region.** `config/models.yaml` calls
  `https://dashscope-us.aliyuncs.com/compatible-mode/v1`. Alibaba's regions page (updated 2026-10-13) lists the
  DashScope domain as *Not supported* for US (Virginia) and asks users to migrate to workspace endpoints
  (`{WorkspaceId}.us-east-1.maas.aliyuncs.com`). On the new path, a workspace's **deployment scope** decides
  where inference runs: *US*, or *Global* (location not stated).
- **To keep drawings in the US**, use a US-scope workspace endpoint for Qwen. Keep `store: false` for OpenAI.
  Ask PARI (O4) whether 30-day abuse-monitoring retention at OpenAI is acceptable.
- **Revisit if** PARI sets data rules, either provider changes its terms, or the Qwen migration changes model
  names or prices.

---

## Question

What do OpenAI and Alibaba Cloud (Qwen) keep from our API calls, for how long, where, and for what?

## Decision It Unblocks

- **Open item O4:** a factual table to share with LatentView and PARI.
- **Risk R10** and assumption A5.
- The Qwen endpoint in `config/models.yaml` (ADR 0004).

## Time Box

`[1]` hour. Used about 1 hour.

## Success Criteria

- [x] One table covering both providers and every endpoint we use, with sources and dates
- [x] A one-paragraph summary ready to send to LatentView
- [x] R10 re-scored; A5 still open until PARI answers O4

---

## Log

### What we send (2026-10-13)

| Provider | Endpoint in `config/models.yaml` | Models | What is sent | Our own controls |
|---|---|---|---|---|
| OpenAI | SDK default (`api.openai.com`), Chat Completions | `gpt-6-astra` (used only with approval) | Page images + extracted text | `store: false` on every request |
| Alibaba Cloud Model Studio | `dashscope-us.aliyuncs.com/compatible-mode/v1` (US, Virginia) | `qwen3-vl-plus` (understanding), `qwen3.8-max` (review, Q&A) | Page images + extracted text (understanding); JSON only (review, Q&A) | None provider-side |

### Findings

| | OpenAI API | Alibaba Cloud Model Studio (US, Virginia) |
|---|---|---|
| **Used for training?** | No, unless we opt in | No: "never uses your data for model training" |
| **Default retention** | Abuse-monitoring logs up to **30 days** (longer if required by law or to prevent harm) | Request data is stored in the region called; **no retention period published** in the docs we found |
| **Application state** | With `store=true`, responses are kept for at least 30 days. With `store=false` (our setting), they are not stored for later retrieval | Console keeps up to 100 conversation records; not relevant to API calls |
| **Where processed** | Not region-bound by default. Data residency (US, EU, UK, Japan, India and others) is available to approved enterprise customers through a regional project | Request and static data stay in the selected region. Inference runs within the workspace's **deployment scope**: *US* or *Global* ("a larger inference resource pool"; countries not listed) |
| **Reduce retention** | Zero Data Retention or Modified Abuse Monitoring, **by prior approval only**. Even then, images flagged by the CSAM classifier are kept for review | None documented beyond regional storage; details deferred to the product terms |
| **Encryption** | Not covered in the pages reviewed | AES-256 for data in transit |
| **Endpoint status** | Current | `dashscope-us.aliyuncs.com` is *Not supported* for US (Virginia) on the current regions page. Migrate to the workspace endpoint. The DashScope domain gets no new features after 2026-09-30 |

### Summary for LatentView / PARI

> To review a drawing, the system sends the drawing's page images and extracted text to an external AI service.
> We use two providers. **OpenAI** does not use API data for training. It keeps inputs and outputs for up to
> 30 days for abuse monitoring, unless the account is approved for Zero Data Retention. We also turn off
> OpenAI's optional response storage. **Alibaba Cloud (Qwen)**, called in its US (Virginia) region, does not use
> customer data for training and stores request data in that region. We can restrict processing to the US by
> using a US-scope workspace, but Alibaba does not publish how long it keeps API request data. On our side,
> drawings and results are deleted when each review session ends. Please let us know whether either provider is
> acceptable to PARI, and whether PARI has rules on retention period or processing location.

### Implications (input, not the decision)

- **Migrate Qwen to a US-scope workspace endpoint** (`{WorkspaceId}.us-east-1.maas.aliyuncs.com`) before any use
  on client drawings outside development. Check in the Model Studio console that the workspace scope is *US*, not
  *Global*, and that `qwen3-vl-plus` and `qwen3.8-max` are available there (model names may change). Then update
  `config/models.yaml`, re-run `di eval understand` on the samples, and record the change in an ADR.
- **Keep `store: false`** for OpenAI. Apply for Zero Data Retention only if PARI requires it.
- **Don't promise "no retention" for either provider.** OpenAI keeps abuse logs for up to 30 days by default, and
  Alibaba's period is unpublished.
- **R10 stays open** until PARI answers O4. Its likelihood goes down (neither provider trains on our data;
  processing location can be controlled), but its impact is unchanged.

### Limits of this spike

- Desk research from public documentation on 2026-10-13. Contract terms (OpenAI's DPA, Alibaba's product terms)
  were not read in full.
- Alibaba's retention period for API request data was not found. It may be in the product terms or require a
  support ticket.
- We did not check which deployment scope our current Qwen key and endpoint actually use.

### Still Open

- PARI's answer to O4: are these providers acceptable, and what retention and location rules apply?
- Alibaba's retention period for API request data (ask Alibaba support or read the product terms).
- The Qwen endpoint migration (see Implications).

---

## Sources (read 2026-10-13)

- OpenAI, *Data controls in the OpenAI platform* — https://developers.openai.com/api/docs/guides/your-data
- OpenAI, *Expanding data residency access to business customers worldwide* —
  https://openai.com/blog/expanding-data-residency-access-to-business-customers-worldwide
- Alibaba Cloud, *Model Studio: Regions and endpoints* (updated 2026-10-13) —
  https://www.alibabacloud.com/help/en/model-studio/regions
- Alibaba Cloud, *Model Studio FAQ* (updated 2026-10-11) —
  https://www.alibabacloud.com/help/en/model-studio/faq-about-alibaba-cloud-model-studio
- Alibaba Cloud, *International Website Product Terms of Service* (referenced by the FAQ, not read in full) —
  https://www.alibabacloud.com/help/en/doc-detail/42416.htm
