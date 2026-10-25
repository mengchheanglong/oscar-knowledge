# MIT OCW source review — 2026-10-25

Only three exact PDFs were approved by the user in this chat, for the shared local
noncommercial hackathon demonstration. Approval does not cover commercial use,
public hosting or other resources. The reusable `manifests/mba_mit.yaml` therefore
keeps **all `approved: false`**. The actual approved manifest, hashes, attribution
and scope are stored privately in ignored `data/mba_courses.yaml`. Original PDFs
stay under ignored `data/raw/mba`; extracted page text and review images stay
under `data/processed/mba`. No course PDF or full extracted text is committed.

MIT's [terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/) state
CC BY-NC-SA 4.0, attribution and share-alike, with rights/third-party limitations.
Original notices and instructor attribution are retained; no MIT endorsement is
claimed. The review does not independently certify rights in every third-party
element. Broader or commercial exposure needs separate curator/rights review.

## Eight-course review

Every course link below was checked on the official site. PDF URLs in the manifest
were followed from actual resource indexes/pages; no download URL was guessed.

| Course | Inspected material | Status and constraints |
| --- | --- | --- |
| [15.390 New Enterprises](https://ocw.mit.edu/courses/15-390-new-enterprises-spring-2013/) | Lecture notes, assignments, video tutorials; Lecture 1 introduces venture planning and opportunity selection | Exact Lecture 1 PDF approved and indexed; no video/transcript download or transcription |
| [15.902 Strategic Management I](https://ocw.mit.edu/courses/15-902-strategic-management-i-fall-2006/) | Lecture notes and assignments; Budget and Aggregate Metrics covers strategy, performance and budgeting | Exact Budget and Aggregate Metrics PDF approved and indexed; dense tables need original-page review |
| [15.810 Marketing Management](https://ocw.mit.edu/courses/15-810-marketing-management-fall-2010/) | Lecture notes, cases, assignments and projects; Lecture 1 contains 5Cs/STP/4Ps and course outline | Exact introductory PDF approved and indexed; linked case readings are not automatically approved or imported |
| [15.431 Entrepreneurial Finance](https://ocw.mit.edu/courses/15-431-entrepreneurial-finance-spring-2011/) | [Selected lecture notes](https://ocw.mit.edu/courses/15-431-entrepreneurial-finance-spring-2011/pages/lecture-notes/) include DCF/VC valuation, real options and deal structure | Direct DCF PDF discovered in resource page; not downloaded/indexed. Some guest PDFs expressly say used with permission; do not assume reuse rights |
| [15.060 Data, Models, and Decisions](https://ocw.mit.edu/courses/15-060-data-models-and-decisions-fall-2014/) | [Lecture summaries](https://ocw.mit.edu/courses/15-060-data-models-and-decisions-fall-2014/pages/lecture-summaries/), assignments, case modules and instructor insights | Site explicitly says lecture notes are unavailable. Summaries are not full instructional lecture notes. Nothing imported |
| [15.010 Economic Analysis for Business Decisions](https://ocw.mit.edu/courses/15-010-economic-analysis-for-business-decisions-fall-2004/) | [Lecture-note index](https://ocw.mit.edu/courses/15-010-economic-analysis-for-business-decisions-fall-2004/pages/lecture-notes/) includes Production and Cost I, demand, pricing, network externalities and game theory | Production and Cost I PDF discovered; unapproved and not imported. Third-party handouts/cases require distinct review |
| [15.311 Organizational Processes](https://ocw.mit.edu/courses/15-311-organizational-processes-fall-2003/) | HTML assignment/project instructions and reading lists | No lecture-note PDF in the inspected menu. Do not mistake assignment logistics for a full management course corpus; nothing imported |
| [15.387 Entrepreneurial Sales](https://ocw.mit.edu/courses/15-387-entrepreneurial-sales-spring-2015/) | [Lecture-note index](https://ocw.mit.edu/courses/15-387-entrepreneurial-sales-spring-2015/pages/lecture-notes/) includes sales calls, prospecting, quotas, freemium models | Lecture 1 Introduction—Diver's Delight PDF discovered; unapproved and not imported |

## Actual imported resources

| Course / instructor | Exact original resource | Physical pages | Active chunks |
| --- | --- | ---: | ---: |
| 15.390, William Aulet and Howard Anderson | [Course Introduction and Objectives & Viable Business Ideas](https://ocw.mit.edu/courses/15-390-new-enterprises-spring-2013/5ebade7cc7014ae6958bd5c48e3ff670_MIT15_390S13_lec01.pdf) | 38 | 38 |
| 15.902, Arnoldo Hax | [Budget and Aggregate Metrics](https://ocw.mit.edu/courses/15-902-strategic-management-i-fall-2006/92d72792ae5e336ac5e6f11a3af4a399_bud_aggmet.pdf) | 11 | 12 |
| 15.810, Natalie Mizik | [Marketing Management, Course Introduction](https://ocw.mit.edu/courses/15-810-marketing-management-fall-2010/49e7dcea0276228cc640de924be6c213_MIT15_810F10_lec01.pdf) | 10 | 11 |

These are three real instructional resources across three subjects, not complete
courses. Financial strategy is present in 15.902; a dedicated finance/economics
lecture is still unapproved. All three have DB status INDEXED, revision 1 and
61 compatible local Qwen vectors in the distinct `mba-mit-demo` collection.
The original synthetic `mba-business` collection remains intact.

## Extraction review

All 59 physical pages yielded nonempty text. The 61 chunks preserve page numbers;
two long pages split without crossing a page boundary. Source hashes were checked
before ingestion, and unchanged re-imports preserved revision/chunk IDs. No OCR
or diagram inference was performed.

The coding agent read extracted instructional pages and visually inspected five
Poppler renders: entrepreneurship p14, strategy p3 and p7, marketing p4 and p6.
No claim of exhaustive visual inspection of all 59 pages is made.

- Strategy p3 is a three-column performance-driver table. Plain extraction loses
  its row/column associations and includes duplicated shadow/overlaid text.
  Pages 10–11 contain numeric tables with similar relationship loss. These are
  flagged in the document's stored usage notes; table calculations are excluded
  from gold judgments. Verify numerical claims against the original page.
- Strategy p7 contains only the budgeting divider heading; this is genuinely
  sparse, not failed extraction. Repeated headers exist on other pages.
- Marketing p2 interleaves its two columns. Page 5 is a syllabus table, not
  substantive pricing instruction. Page 6 supplies a readable framework list;
  page 4 shows equivalent framework names in a diagram and is accepted as an
  alternative gold location. OCR/visual interpretation is not claimed.
- Images and diagrams are not fully represented by extracted text. The small
  sample does not establish a general PDF/table extraction guarantee.

The private review JSON records per-page character counts, exact SHA256 hashes,
raw locations and approval scope. DB provenance stores course, institution,
source URL, document type, license and notes. Retrieval/OSCAR citations retain
actual chunk/document IDs, revision, page locator and original PDF URL.
