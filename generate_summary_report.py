import os
import sys
import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# Define modern cohesive color palette
PRIMARY_COLOR = colors.HexColor("#0f172a")    # Slate 900 (deep dark blue/grey)
SECONDARY_COLOR = colors.HexColor("#0284c7")  # Sky 600 (vibrant blue)
TEXT_COLOR = colors.HexColor("#334155")       # Slate 700 (dark charcoal body text)
LIGHT_BG = colors.HexColor("#f8fafc")         # Slate 50 (soft light background)
BORDER_COLOR = colors.HexColor("#e2e8f0")     # Slate 200 (subtle grey border)
SUCCESS_COLOR = colors.HexColor("#16a34a")    # Green 600
CODE_COLOR = colors.HexColor("#0f172a")       # Dark background for code block
CODE_TEXT_COLOR = colors.HexColor("#38bdf8")  # Cyan for code text

class NumberedCanvas(canvas.Canvas):
    """
    A canvas that enables dynamic two-pass page numbering ("Page X of Y")
    and draws professional running headers and footers on all pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Running Header
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(PRIMARY_COLOR)
        self.drawString(54, 745, "CLINICAL CONSULTATION COPILOT")
        
        self.setFont("Helvetica", 8)
        self.setFillColor(TEXT_COLOR)
        self.drawRightString(558, 745, "END-TO-END OPERATIONAL LIFECYCLE")
        
        # Header Line
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.75)
        self.line(54, 737, 558, 737)
        
        # Running Footer Line
        self.line(54, 54, 558, 54)
        
        # Running Footer Text
        self.drawString(54, 40, "Confidential - Operational Specification")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        
        self.restoreState()

def create_report(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,  # Give room for running header
        bottomMargin=72 # Give room for running footer
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Typography Styles
    styles.add(ParagraphStyle(
        'DocTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=PRIMARY_COLOR,
        spaceBefore=5,
        spaceAfter=3,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'DocSubtitle',
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=SECONDARY_COLOR,
        spaceAfter=10,
        keepWithNext=True
    ))
    
    styles.add(ParagraphStyle(
        'Heading1_Custom',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=PRIMARY_COLOR,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    ))
    
    styles.add(ParagraphStyle(
        'Heading2_Custom',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=SECONDARY_COLOR,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        'Body_Custom',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_COLOR,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        'Bullet_Custom',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_COLOR,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    ))

    styles.add(ParagraphStyle(
        'Code_Block',
        fontName='Courier',
        fontSize=7,
        leading=9,
        textColor=CODE_TEXT_COLOR,
        spaceAfter=0
    ))

    styles.add(ParagraphStyle(
        'Table_Cell',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=TEXT_COLOR
    ))

    styles.add(ParagraphStyle(
        'Table_Cell_Header',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white
    ))

    story = []

    # =========================================================================
    # DOCUMENT HEADER
    # =========================================================================
    story.append(Paragraph("Clinical Consultation Copilot", styles['DocTitle']))
    story.append(Paragraph("Chronological Operational Specification: Ingestion to Downstream LLM Synthesis", styles['DocSubtitle']))
    
    # Metadata bar
    today_str = datetime.date.today().strftime("%B %d, %Y")
    meta_text = f"<b>Date:</b> {today_str} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Operational Status:</b> Fully Verified &nbsp;&nbsp;|&nbsp;&nbsp; <b>Process Pipeline:</b> Step 1 to Step 4 &rArr; LLM"
    story.append(Paragraph(meta_text, styles['Body_Custom']))
    
    # Simple line separator
    line_data = [['']]
    line_table = Table(line_data, colWidths=[7.0*inch], rowHeights=[1.5])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), SECONDARY_COLOR),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 8))

    # =========================================================================
    # PHASE 1: SESSION INITIALIZATION & CLIENT HANDSHAKE
    # =========================================================================
    story.append(Paragraph("Phase 1: Session Handshake & Connection Initialization", styles['Heading1_Custom']))
    story.append(Paragraph(
        "The operational lifecycle begins at the client application edge. When a clinician begins a new consultation "
        "session, the client application (Web or Mobile) establishes a connection to the backend:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>Connection Handshake:</b> The client initiates a secure full-duplex WebSocket connection to the backend gateway at "
        "<code>wss://[host]/v1/streaming/audio</code>.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Query Parameter Authentication:</b> The handshake contains three critical query parameters: "
        "<code>session_id</code> (a unique UUID representing the consultation), <code>role</code> (identifying the participant as "
        "<code>doctor</code>, <code>patient</code>, or <code>attender</code>), and a secure <code>token</code>.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Active Registry Binding:</b> The <code>SessionManager</code> validates the JWT token, verifies that the session is active, "
        "and registers the WebSocket connection, binding it to the specific participant role in-memory.",
        styles['Bullet_Custom']
    ))

    # =========================================================================
    # PHASE 2: REAL-TIME AUDIO INGESTION & DYNAMIC BUFFERING
    # =========================================================================
    story.append(Paragraph("Phase 2: Real-Time Audio Streaming & In-Memory Buffering", styles['Heading1_Custom']))
    story.append(Paragraph(
        "Once authenticated, the WebSocket connection transitions into a continuous data streaming mode:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>Raw Audio Capture:</b> The client captures audio in a raw, uncompressed format: <b>Linear PCM (LPCM) 16-bit, 16kHz, Mono</b>. "
        "This ensures maximum phonetic clarity for the transcription engine and bypasses compression CPU overhead on the device.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Micro-Frame Streaming:</b> The client streams the audio in tiny slices (20ms to 50ms per packet; i.e., 640 to 1600 bytes) "
        "to maintain an ultra-low local capture latency and avoid network queue delays.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>On-the-Fly Byte Validation:</b> On the backend, the <code>AudioFrameValidator</code> inspects each incoming binary packet "
        "to ensure it adheres to a 2-byte sample boundary and falls within the expected size constraints, rejecting corrupted frames.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Stable Chunk Accumulation:</b> The <code>AudioSessionBuffer</code> accumulates these tiny micro-frames in a high-speed "
        "in-memory <code>bytearray</code>. When the buffer reaches exactly **1.0 second of audio (32,000 bytes)**, it packages the chunk "
        "and pushes it to a role-specific <code>asyncio.Queue</code>.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Memory Protection & Backpressure:</b> Each stream is capped at a strict <b>10MB memory threshold</b>. If network congestion "
        "or processing delays block the queue, the buffer triggers backpressure policies (e.g., <code>drop_oldest</code>) to prevent RAM exhaustion.",
        styles['Bullet_Custom']
    ))

    story.append(PageBreak())

    # =========================================================================
    # PHASE 3: REAL-TIME SPEECH-TO-TEXT (STT) TRANSCRIPTION
    # =========================================================================
    story.append(Paragraph("Phase 3: Real-Time Speech-to-Text (STT) Pipeline", styles['Heading1_Custom']))
    story.append(Paragraph(
        "Once a stable 1.0-second audio chunk is queued, the transcription layer processes it asynchronously:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>Stateless STT Reconciliation Loop:</b> A background <code>STTManager</code> runs a continuous 100ms loop, monitoring "
        "the active session registry. It dynamically spawns dedicated background worker tasks for each newly connected role and tears "
        "them down when the connection closes.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>WebSocket Streaming to STT Provider:</b> The spawned worker task reads the 1.0s chunks from the queue and streams them "
        "over a persistent WebSocket connection to a high-accuracy speech-to-text service (such as ElevenLabs Scribe V2 or Whisper).",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Self-Healing Connections:</b> The worker task implements a robust **120-second timeout guard**. If the STT provider's "
        "socket hangs or disconnects due to network jitter, the worker automatically re-establishes the socket connection and flushes "
        "the local buffer, preventing conversational data loss.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Transcript Bus Dispatch:</b> As transcription results are returned, they are parsed and published to a thread-safe, "
        "in-memory <code>TranscriptBus</code>, making the text events available to downstream processors.",
        styles['Bullet_Custom']
    ))

    # =========================================================================
    # PHASE 4: SPEAKER DIARIZATION & TEMPORAL ALIGNMENT
    # =========================================================================
    story.append(Paragraph("Phase 4: Speaker Diarization & Temporal Alignment", styles['Heading1_Custom']))
    story.append(Paragraph(
        "Transcription alone is insufficient for multi-party consultations; the system must attribute text to the correct speakers:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>In-Memory Tensor Diarization:</b> The <code>diarization_worker</code> processes the raw audio stream. It normalizes peak "
        "amplitudes in-memory and converts the raw LPCM bytes directly into numerical PyTorch tensors, feeding them into the "
        "<code>pyannote/speaker-diarization-3.1</code> model (running on CUDA/CPU) without writing slow temporary files to disk.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>4-Tier Temporal Cascade:</b> Due to the acoustic complexity of clinical environments (e.g., interruptions, doctor and patient "
        "speaking at once), the <code>SpeakerTimeline</code> engine resolves overlapping speech using a strict 4-tier assignment cascade:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;1. <i>Overlap Resolution:</i> Determines dominant speaker energy during overlapping segments.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;2. <i>Proximity Assignment:</i> Attributes unassigned words to the nearest active speaker segment.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;3. <i>Continuity Mapping:</i> Bridges short pauses to maintain conversational flow.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;4. <i>Hard Caps:</i> Prevents single-speaker turns from extending past maximum reasonable limits.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Word-Level Timestamp Alignment:</b> The engine aligns individual words from the STT stream with the physical "
        "diarized speaker boundaries, producing a chronologically aligned chronological transcript (e.g., attributing word arrays to the "
        "doctor, patient, or attender).",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Utterance Merging & Filler Stripping:</b> Consecutive turns by the same speaker are merged into a single dialogue block, "
        "and conversational filler words (e.g., <i>'uh'</i>, <i>'um'</i>, <i>'like'</i>) are stripped out by the <code>FillerRemover</code>.",
        styles['Bullet_Custom']
    ))

    story.append(PageBreak())

    # =========================================================================
    # PHASE 5: LOCAL CLINICAL FACT EXTRACTION & RULES ENGINE
    # =========================================================================
    story.append(Paragraph("Phase 5: Local Clinical Fact Extraction & Rules Engine", styles['Heading1_Custom']))
    story.append(Paragraph(
        "The clean, aligned dialogue turns are immediately pushed to the <code>ClinicalProcessingPipeline</code>. "
        "This layer executes a high-speed, local rules engine to extract structured medical concepts:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>Clinician Question Suppression:</b> Before extracting findings, the engine inspects the speaker ID. "
        "If the speaker is the doctor and the utterance is classified as a question (e.g., <i>'Do you have a fever?'</i>), the engine "
        "suppresses the turn. This ensures that clinical queries do not register as active patient symptoms.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Layman Term Normalization:</b> The <code>ClinicalNormalizer</code> standardizes colloquial patient descriptions to clinical concepts "
        "(e.g., translating <i>'head ache'</i> or <i>'throbbing head'</i> to <i>'headache'</i>, and <i>'watery pills'</i> to <i>'amlodipine'</i>).",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Atomic Entity Extraction:</b> Programmatic regular expression patterns match terms against six clinical categories: "
        "Symptoms, Medications, Diagnoses, Procedures, Risk Factors, and Family Histories.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Clause-Isolated Negation Resolution:</b> The text is split into clauses. The engine evaluates pre-negation triggers "
        "(e.g., <i>'denies'</i>, <i>'no'</i>, <i>'without'</i>) and post-negation triggers (e.g., <i>'resolved'</i>, <i>'ruled out'</i>). "
        "It correctly identifies double-negations (e.g., <i>'Fever was not ruled out today'</i> resolves to <code>present: true</code>).",
        styles['Bullet_Custom']
    ))

    # =========================================================================
    # PHASE 6: SESSION-LEVEL STATE AGGREGATION
    # =========================================================================
    story.append(Paragraph("Phase 6: Session-Level State Aggregation & Deduplication", styles['Heading1_Custom']))
    story.append(Paragraph(
        "To compile a cohesive summary, individual turn extractions are continuously aggregated into a session-level state database:",
        styles['Body_Custom']
    ))
    story.append(Paragraph(
        "• <b>Incremental Deduplication:</b> When a symptom or medication is extracted multiple times across a session, the aggregator "
        "deduplicates it, preventing redundant entries in the clinical record.",
        styles['Bullet_Custom']
    ))
    story.append(Paragraph(
        "• <b>Attribute Reconcilation:</b> The aggregator merges attributes from different turns. If the patient mentions a <i>'headache'</i> "
        "early in the session, and later specifies it is <i>'severe'</i> and has lasted <i>'two weeks'</i>, the engine updates the "
        "existing headache entity with the new severity and duration.",
        styles['Bullet_Custom']
    ))
    
    story.append(Paragraph("Aggregated Session State Output Payload (Example):", styles['Heading2_Custom']))
    
    # JSON Block
    sample_json = [
        "{",
        "  \"session_id\": \"consultation-session-001\",",
        "  \"symptoms\": [",
        "    { \"name\": \"headache\", \"severity\": \"severe\", \"duration\": \"two weeks\", \"present\": true, \"confidence\": 1.0 },",
        "    { \"name\": \"dizziness\", \"severity\": null, \"duration\": null, \"present\": true, \"confidence\": 1.0 },",
        "    { \"name\": \"fever\", \"severity\": null, \"duration\": null, \"present\": false, \"confidence\": 1.0 }",
        "  ],",
        "  \"medications\": [",
        "    { \"name\": \"paracetamol\", \"present\": true, \"confidence\": 1.0 },",
        "    { \"name\": \"amlodipine\", \"present\": true, \"confidence\": 1.0 }",
        "  ],",
        "  \"diagnoses\": [",
        "    { \"name\": \"hypertension\", \"present\": true, \"confidence\": 1.0 },",
        "    { \"name\": \"migraine\", \"present\": true, \"confidence\": 1.0 }",
        "  ]",
        "}"
    ]
    code_rows = []
    for line in sample_json:
        clean_line = line.replace(" ", "&nbsp;").replace("<", "&lt;").replace(">", "&gt;")
        code_rows.append([Paragraph(clean_line, styles['Code_Block'])])
    code_table = Table(code_rows, colWidths=[7.0 * inch])
    code_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), CODE_COLOR),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(code_table)

    story.append(PageBreak())

    # =========================================================================
    # PHASE 7: CONTEXT-DRIVEN DOWNSTREAM LLM TRIGGERING
    # =========================================================================
    story.append(Paragraph("Phase 7: Context-Driven Downstream LLM Triggering (The End)", styles['Heading1_Custom']))
    story.append(Paragraph(
        "The final phase of the operational workflow is the transition from Tier 1 (Local Rule Engine) to Tier 2 (LLM Engine). "
        "The system evaluates the context accumulated in the session-level state, triggering a downstream LLM call "
        "only when one of these five specific triggering conditions is met:",
        styles['Body_Custom']
    ))

    trigger_details = [
        ("1. Session End / Flush", "<b>Trigger Criteria:</b> The clinician explicitly clicks 'End Consultation', 'Generate Note', or the WebSocket connection closes.<br/>"
                                  "<b>LLM Action:</b> Receives the full dialogue transcript and the structured state payload to synthesize the final clinical note (EHR or SOAP format), formatting it into a professional layout."),
        
        ("2. Section Transition", "<b>Trigger Criteria:</b> The local parser detects a conversational transition between major clinical sections (e.g., from subjective HPI to objective physical exam).<br/>"
                                  "<b>LLM Action:</b> Generates a targeted, sectional summary in the background, updating the draft EHR note incrementally."),
        
        ("3. Inactivity Pause", "<b>Trigger Criteria:</b> The audio streaming layer detects a continuous silence period of 10 to 15 seconds across all active channels (e.g., doctor examining patient).<br/>"
                                "<b>LLM Action:</b> Runs an intermediate background summary task, catching up on the consultation draft without interrupting the active conversation flow."),
        
        ("4. Semantic Density", "<b>Trigger Criteria:</b> The local aggregator collects a density of 5+ new clinical findings or 10-15 conversational dialogue turns.<br/>"
                                "<b>LLM Action:</b> Evaluates the new segment, updates the global state, and reconciles any contradictions or patient self-corrections."),
        
        ("5. Safety Alert (Override)", "<b>Trigger Criteria:</b> The local rules engine extracts a critical clinical emergency (e.g., 'chest pain', 'anaphylaxis') or a dangerous drug-drug interaction.<br/>"
                                      "<b>LLM Action:</b> Bypasses all buffering queues, performs an immediate safety audit, and flashes a high-priority warning directly onto the clinician's screen.")
    ]

    t_rows = [
        [Paragraph("Trigger Condition", styles['Table_Cell_Header']), 
         Paragraph("Threshold Criteria & Asynchronous LLM Action", styles['Table_Cell_Header'])]
    ]
    for name, desc in trigger_details:
        t_rows.append([
            Paragraph(f"<b>{name}</b>", styles['Table_Cell']),
            Paragraph(desc, styles['Table_Cell'])
        ])

    t_table = Table(t_rows, colWidths=[1.8*inch, 5.2*inch])
    t_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT_BG]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SYSTEM CONCLUSION
    # =========================================================================
    story.append(Paragraph("System Conclusion & Operational Validation", styles['Heading1_Custom']))
    conclusion_text = (
        "By structuring the backend into a chronological, 7-phase operational lifecycle, the Clinical Consultation Copilot "
        "succeeds in balancing high-performance, real-time interactivity with intelligent, context-driven synthesis. "
        "The Tier 1 local rule engine handles immediate, low-latency, deterministic filtering and extraction, "
        "while the Tier 2 LLM engine is triggered selectively when sufficient conversational context has accumulated. "
        "This hybrid pipeline minimizes API latency, reduces operational costs by up to 90%, and enforces strict clinical safety standards."
    )
    story.append(Paragraph(conclusion_text, styles['Body_Custom']))

    # Build PDF using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)

if __name__ == "__main__":
    pdf_filename = "clinical_copilot_overall_summary.pdf"
    create_report(pdf_filename)
    print(f"Successfully generated chronological operational PDF: {pdf_filename}")
