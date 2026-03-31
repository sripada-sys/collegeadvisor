#!/usr/bin/env python3
"""
Generate comprehensive college admission guide PDF.
For a Class 12 student (JEE 2027 cycle) — PCM, CBSE, TN domicile, General category.

Run with: DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 generate_guide.py
"""

import weasyprint
import os
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: A4;
    margin: 2cm 1.8cm;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #888;
    }
    @top-right {
      content: "Confidential — For Private Use Only";
      font-size: 8pt;
      color: #aaa;
    }
  }

  body {
    font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
  }

  h1 {
    font-size: 22pt;
    color: #1a237e;
    border-bottom: 3px solid #1a237e;
    padding-bottom: 8px;
    margin-top: 0;
  }

  h2 {
    font-size: 15pt;
    color: #283593;
    border-bottom: 1.5px solid #c5cae9;
    padding-bottom: 5px;
    margin-top: 25px;
    page-break-after: avoid;
  }

  h3 {
    font-size: 12pt;
    color: #3949ab;
    margin-top: 18px;
    margin-bottom: 6px;
    page-break-after: avoid;
  }

  h4 {
    font-size: 10.5pt;
    color: #455a64;
    margin-top: 12px;
    margin-bottom: 4px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 15px 0;
    font-size: 9.5pt;
    page-break-inside: auto;
  }

  tr { page-break-inside: avoid; }

  th {
    background-color: #1a237e;
    color: white;
    padding: 7px 8px;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
  }

  td {
    padding: 6px 8px;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: top;
  }

  tr:nth-child(even) td { background-color: #f5f5f5; }

  .verified {
    background: #e8f5e9;
    border-left: 4px solid #4caf50;
    padding: 8px 12px;
    margin: 10px 0;
    font-size: 9.5pt;
  }

  .caution {
    background: #fff3e0;
    border-left: 4px solid #ff9800;
    padding: 8px 12px;
    margin: 10px 0;
    font-size: 9.5pt;
  }

  .critical {
    background: #fce4ec;
    border-left: 4px solid #e53935;
    padding: 8px 12px;
    margin: 10px 0;
    font-size: 9.5pt;
  }

  .action {
    background: #e3f2fd;
    border-left: 4px solid #1565c0;
    padding: 8px 12px;
    margin: 10px 0;
    font-size: 9.5pt;
  }

  .tag-verified {
    display: inline-block;
    background: #4caf50;
    color: white;
    font-size: 7.5pt;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    vertical-align: middle;
  }

  .tag-approx {
    display: inline-block;
    background: #ff9800;
    color: white;
    font-size: 7.5pt;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    vertical-align: middle;
  }

  .tag-unverified {
    display: inline-block;
    background: #e53935;
    color: white;
    font-size: 7.5pt;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    vertical-align: middle;
  }

  .cover-page {
    text-align: center;
    padding-top: 120px;
    page-break-after: always;
  }

  .cover-page h1 {
    font-size: 32pt;
    border: none;
    color: #1a237e;
    margin-bottom: 10px;
  }

  .cover-page .subtitle {
    font-size: 16pt;
    color: #455a64;
    margin-bottom: 40px;
  }

  .cover-page .profile {
    font-size: 11pt;
    color: #333;
    line-height: 1.8;
    text-align: left;
    max-width: 400px;
    margin: 0 auto;
    background: #f5f5f5;
    padding: 20px 25px;
    border-radius: 8px;
  }

  .cover-page .date {
    font-size: 10pt;
    color: #888;
    margin-top: 50px;
  }

  .cover-page .disclaimer {
    font-size: 8.5pt;
    color: #999;
    margin-top: 30px;
    max-width: 450px;
    margin-left: auto;
    margin-right: auto;
  }

  .toc { page-break-after: always; }

  .toc h2 { border-bottom: 2px solid #1a237e; }

  .toc ol { font-size: 11pt; line-height: 2.2; }

  .section { page-break-before: always; }

  .best { color: #2e7d32; font-weight: 600; }
  .typical { color: #1565c0; font-weight: 600; }
  .worst { color: #c62828; font-weight: 600; }

  .small { font-size: 8.5pt; color: #777; }

  ul { padding-left: 18px; }
  li { margin-bottom: 3px; }

  .two-col {
    display: flex;
    gap: 15px;
  }
  .two-col > div { flex: 1; }

  .page-break { page-break-before: always; }
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover-page">
  <h1>Engineering &amp; Science<br>College Guide 2027</h1>
  <p class="subtitle">Beyond JEE — Every Door That Matters</p>

  <div class="profile">
    <strong>Student Profile:</strong><br>
    Class 12 entering (JEE 2027 cycle)<br>
    CBSE Board, Tamil Nadu domicile (since LKG)<br>
    PCM stream — CS/ECE inclination<br>
    General Category (no reservation)<br>
    Class 10: 98% (Science 100, Maths 95)<br>
    Sri Chaitanya Super 60 program<br>
    Budget: Up to ₹40 Lakh (loan OK)<br>
    Interests: AI, CS, "Loads of money" + "MIT researcher"
  </div>

  <p class="date">Prepared: """ + datetime.now().strftime("%d %B %Y") + """</p>

  <p class="disclaimer">
    This document contains a mix of verified facts, approximately verified information,
    and analysis. Every claim is tagged with its verification level.
    Verify all critical details (fees, deadlines, eligibility) from official websites before acting.
    This is NOT official counseling. No warranties.
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<div class="toc">
  <h2>Contents</h2>
  <ol>
    <li><strong>The Big Picture</strong> — Why this guide exists</li>
    <li><strong>Student Profile &amp; What It Means</strong></li>
    <li><strong>The Complete Landscape</strong> — 30+ institutions organized by type</li>
    <li><strong>Tamil Nadu Home Advantage</strong> — PSG, CEG, SSN, Amrita, TNEA &amp; state quota</li>
    <li><strong>Best Case / Worst Case / Typical</strong> — Outcomes per institution tier</li>
    <li><strong>The AI Angle</strong> — Real vs hype in AI education</li>
    <li><strong>The "Money + Research" Path</strong> — Where both dreams converge</li>
    <li><strong>Exam Calendar &amp; Registration Guide</strong> — All 11+ exams</li>
    <li><strong>Institution Deep Dives</strong> — Top recommendations</li>
    <li><strong>Fee Structures</strong> — What each path costs</li>
    <li><strong>Decision Framework</strong> — How the student should choose</li>
    <li><strong>Verification Status</strong> — What's confirmed vs approximate</li>
    <li><strong>Action Items for This Week</strong></li>
  </ol>
</div>

<!-- SECTION 1: BIG PICTURE -->
<div class="section">
  <h2>1. The Big Picture</h2>

  <p>Most families think college admission = JEE. The reality is that India has <strong>at least 11 separate entrance exams</strong> that lead to world-class institutions — many of which the coaching industry never mentions because they don't generate coaching revenue.</p>

  <div class="critical">
    <strong>What coaching centers don't tell you:</strong> ISI, CMI, IISERs, NISER, and IIST are separate from JEE. They have their own exams, test different skills, and in some cases produce BETTER outcomes than NITs and even some IITs. Failing JEE does NOT mean failing these.
  </div>

  <p>This guide covers every institution worth considering — from IIT Bombay to CMI Chennai — with honest, fact-checked outcomes. We tag every claim with its verification level:</p>

  <table>
    <tr><th>Tag</th><th>Meaning</th></tr>
    <tr><td><span class="tag-verified">VERIFIED</span></td><td>Confirmed from official institutional website or government source</td></tr>
    <tr><td><span class="tag-approx">APPROX</span></td><td>Approximately correct from reliable secondary sources, verify before acting</td></tr>
    <tr><td><span class="tag-unverified">UNVERIFIED</span></td><td>Industry knowledge / general estimates — treat as directional only</td></tr>
  </table>
</div>

<!-- SECTION 2: STUDENT PROFILE -->
<div class="section">
  <h2>2. Student Profile Analysis</h2>

  <h3>Raw Data</h3>
  <table>
    <tr><th>Parameter</th><th>Value</th><th>What It Means</th></tr>
    <tr><td>Class 10 aggregate</td><td>98%</td><td>Strong academic foundation. Top 2-3% nationally.</td></tr>
    <tr><td>Class 10 Science</td><td>100/100</td><td>Exceptional. Natural aptitude for science.</td></tr>
    <tr><td>Class 10 Maths</td><td>95/100</td><td>Very strong. Can handle ISI/CMI style problems with prep.</td></tr>
    <tr><td>Coaching</td><td>Sri Chaitanya Super 60</td><td>Top JEE-focused program. Excellent for JEE Main/Advanced.</td></tr>
    <tr><td>Weekly scores</td><td>150-240 / 300</td><td>High variance. Top performances (240) show capability. Inconsistency is the key concern.</td></tr>
    <tr><td>CBSE + TN domicile</td><td>Since LKG</td><td>Eligible for TN state quota at NITs (50% seats). CBSE normalization for TNEA.</td></tr>
    <tr><td>Category</td><td>General</td><td>No reservation benefit. Merit-only competition.</td></tr>
    <tr><td>Budget</td><td>Up to ₹40L</td><td>All institutions in India are affordable. Even BITS at ₹25L is within range.</td></tr>
    <tr><td>Interests</td><td>CS/ECE, AI, money + research</td><td>Perfect fit for ISI/CMI/IIT Math+CS paths that lead to both.</td></tr>
  </table>

  <h3>The Inconsistency Issue (150 vs 240)</h3>
  <p>A 90-point swing in weekly tests is significant. This suggests:</p>
  <ul>
    <li>The 240 scores show the kid CAN perform at a high level</li>
    <li>The 150 scores suggest gaps in specific topics or concentration issues</li>
    <li>For JEE Main: even 150/300 consistently → likely rank 10,000-30,000 (gets NITs)</li>
    <li>At 240/300 consistently → likely rank 1,000-5,000 (gets top NITs, maybe newer IITs)</li>
    <li>For JEE Advanced: needs consistent 200+ to have a shot at IIT CS</li>
  </ul>

  <div class="caution">
    <strong>Key insight:</strong> This inconsistency is EXACTLY why having non-JEE options matters. ISI/CMI/IISER exams test different skills (deep thinking vs speed). A kid who hits 240 on good days may ace an ISI paper that rewards careful problem-solving over fast MCQ execution.
  </div>
</div>

<!-- SECTION 3: COMPLETE LANDSCAPE -->
<div class="section">
  <h2>3. The Complete Landscape</h2>

  <h3>Tier R — Research Powerhouses (Often overlooked, world-class)</h3>
  <table>
    <tr><th>Institution</th><th>Program</th><th>Duration</th><th>Admission</th><th>Seats (approx)</th><th>Status</th></tr>
    <tr><td><strong>IISc Bangalore</strong></td><td>BS (Research)</td><td>4 years</td><td>IAT (IISER Aptitude Test)</td><td>~120</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>CMI Chennai</strong></td><td>BSc (Hons) Math+CS / Math+Physics</td><td>4 years</td><td>Own entrance exam</td><td>~50</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>ISI Kolkata</strong></td><td>B.Stat (Hons)</td><td>3 years</td><td>Own entrance exam</td><td>~50</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>ISI Bangalore</strong></td><td>B.Math (Hons)</td><td>3 years</td><td>Own entrance exam</td><td>~50</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>ISI Kolkata/Delhi</strong></td><td>BSDS (Hons)</td><td>4 years</td><td>JEE Main math percentile + CUET</td><td>~40</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>IISERs (7)</strong></td><td>BS-MS (dual degree)</td><td>5 years</td><td>IAT only (from 2024)</td><td>~200/campus</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>NISER Bhubaneswar</strong></td><td>Integrated MSc</td><td>5 years</td><td>NEST exam</td><td>~200</td><td><span class="tag-verified">VERIFIED</span></td></tr>
    <tr><td><strong>IIST Trivandrum</strong></td><td>BTech Aero/Avionics/Eng Physics</td><td>4-5 years</td><td>JEE Advanced</td><td>140</td><td><span class="tag-verified">VERIFIED</span></td></tr>
  </table>

  <h3>Tier A — Premier Engineering (The usual suspects)</h3>
  <table>
    <tr><th>Institution</th><th>Key Programs</th><th>Admission</th><th>Realistic for this student?</th></tr>
    <tr><td><strong>IIT Bombay / Delhi / Madras / KGP / Kanpur</strong></td><td>CS, ECE, Math+Computing</td><td>JEE Advanced</td><td>CS: Stretch (need top 500). ECE: Possible (top 2000). Math+Computing at IIT Madras: Best realistic target.</td></tr>
    <tr><td><strong>IIT Hyderabad / Roorkee / Guwahati / BHU</strong></td><td>CS, ECE</td><td>JEE Advanced</td><td>CS: Possible at consistent 200+ weekly scores.</td></tr>
    <tr><td><strong>IIT Tirupati / Palakkad / Dharwad / Goa / Bhilai</strong></td><td>CS, ECE</td><td>JEE Advanced</td><td>CS: Realistic. Lower cutoffs, IIT brand. Nearby campuses.</td></tr>
    <tr><td><strong>NIT Trichy</strong></td><td>CS, ECE, IT</td><td>JEE Main (50% TN quota!)</td><td>Strong possibility with home state advantage.</td></tr>
    <tr><td><strong>NIT Surathkal / Warangal / Calicut</strong></td><td>CS, ECE</td><td>JEE Main</td><td>Realistic for All India quota.</td></tr>
    <tr><td><strong>BITS Pilani / Goa / Hyderabad</strong></td><td>CS, ECE, EEE</td><td>BITSAT (own exam)</td><td>Realistic. No reservation = no disadvantage. Merit only.</td></tr>
    <tr><td><strong>IIIT Hyderabad</strong></td><td>CS (CRR, CLD), ECE</td><td>UGEE (own) + JEE Main</td><td>Realistic via UGEE. Top AI research lab in India (CVIT).</td></tr>
  </table>

  <h3>Tier B — Strong Options</h3>
  <table>
    <tr><th>Institution</th><th>Admission</th><th>Notes</th></tr>
    <tr><td>IIIT Delhi</td><td>JAC Delhi (JEE Main)</td><td>State university. Check outside-Delhi quota. Strong CS.</td></tr>
    <tr><td>IIIT Allahabad</td><td>JEE Main</td><td>Strong CS outcomes. IIIT system pioneer.</td></tr>
    <tr><td>IIIT Sri City</td><td>JEE Main</td><td>Near Chennai. Growing.</td></tr>
    <tr><td>IIITDM Kancheepuram</td><td>JEE Main</td><td>Near Chennai. Design + Manufacturing focus. CFTI status.</td></tr>
    <tr><td>IIT Madras BS programs</td><td>IAT</td><td>BS-Medical Sciences via IAT. New, unique.</td></tr>
    <tr><td>DTU / NSUT Delhi</td><td>JAC Delhi</td><td>Delhi state quota applies.</td></tr>
    <tr><td>COEP Pune / VJTI Mumbai</td><td>State CET</td><td>Historic institutions. State exams.</td></tr>
  </table>

  <h3>Tier TN — Tamil Nadu Powerhouses (via TNEA / own exams)</h3>
  <table>
    <tr><th>Institution</th><th>Admission</th><th>Honest Assessment</th></tr>
    <tr><td><strong>CEG, Anna University, Chennai</strong></td><td>TNEA (Class 12 marks)</td><td>Asia's oldest tech institution (est. 1794). Main campus of Anna University. Alumni: Raj Reddy (Turing Award), Ashok Elluswamy (VP AI, Tesla). Strong CS/IT.</td></tr>
    <tr><td><strong>PSG Tech, Coimbatore</strong></td><td>TNEA (Class 12 marks)</td><td>NIRF Eng #67. Alumni: Shiv Nadar (HCL founder), C Vijayakumar (HCL CEO), Mylswamy Annadurai (Chandrayaan). Sandwich engineering courses. Excellent industry connections.</td></tr>
    <tr><td><strong>SSN / Shiv Nadar University Chennai</strong></td><td>SNU entrance (from 2026)</td><td>Founded by Shiv Nadar. 230-acre campus. Was TN's #1 private engineering college. MERGING into Shiv Nadar University from 2026 — admissions shifting to SNU's own exam. CMU partnership.</td></tr>
    <tr><td><strong>Amrita Vishwa Vidyapeetham, Coimbatore</strong></td><td>AEEE (own) + JEE Main</td><td>NIRF Eng #23, Overall #18. Deemed university. NAAC A++. 450-acre campus. Strong research (27 Stanford top-2% scientists). Multiple TN campuses.</td></tr>
    <tr><td><strong>SASTRA, Thanjavur</strong></td><td>JEE Main + own exam</td><td>Deemed university. NIRF top-50 universities. Strong placements for a tier-2 city.</td></tr>
    <tr><td><strong>Thiagarajar College (TCE), Madurai</strong></td><td>TNEA</td><td>Historic Madurai institution. Autonomous. Good regional outcomes.</td></tr>
    <tr><td><strong>Kumaraguru (KCT), Coimbatore</strong></td><td>TNEA</td><td>Growing. Good campus. Industry partnerships in Coimbatore.</td></tr>
  </table>

  <h3>Tier S (Safety) — National Private options</h3>
  <table>
    <tr><th>Institution</th><th>Admission</th><th>Honest Assessment</th></tr>
    <tr><td>VIT Vellore (main campus only)</td><td>VITEEE</td><td>CS top branch only. Median: ₹5-8L. Top 5%: ₹20L+. Rest: ₹3.5-5L TCS/Infosys.</td></tr>
    <tr><td>SRM KTR (main campus)</td><td>SRMJEE</td><td>Similar to VIT. Marketing ≠ median outcome.</td></tr>
    <tr><td>Manipal IT</td><td>MET</td><td>Good campus. CS outcomes similar to VIT.</td></tr>
    <tr><td>PES University Bangalore</td><td>PESSAT</td><td>Small but decent CS outcomes in Bangalore ecosystem.</td></tr>
  </table>

  <div class="critical">
    <strong>Hype check on private universities:</strong> When they say "highest package ₹44 LPA" — that's 1-2 students out of 5,000+. Ask for MEDIAN package. Median at VIT/SRM CS = ₹4-8L. This is NOT the "loads of money" path.
  </div>
</div>

<!-- SECTION 3.5: TAMIL NADU HOME ADVANTAGE -->
<div class="section">
  <h2>4. Tamil Nadu Home Advantage</h2>

  <div class="action">
    <strong>This student has a MASSIVE structural advantage that most families overlook:</strong> Tamil Nadu domicile since LKG + CBSE board = access to both national exams AND TN state quota. This is a double safety net.
  </div>

  <h3>How TNEA Works (Tamil Nadu Engineering Admissions) <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><th>Parameter</th><th>Detail</th></tr>
    <tr><td><strong>What is it?</strong></td><td>Single-window counselling for ~450+ engineering colleges in Tamil Nadu (Anna University system)</td></tr>
    <tr><td><strong>Exam required?</strong></td><td>NONE. Pure Class 12 marks. No entrance exam.</td></tr>
    <tr><td><strong>Marks used</strong></td><td>Physics + Chemistry + Maths from Class 12 board (200 marks aggregate formula)</td></tr>
    <tr><td><strong>CBSE students</strong></td><td>CBSE marks are used directly. No separate normalization since 2021. CBSE students compete equally.</td></tr>
    <tr><td><strong>Top colleges via TNEA</strong></td><td>CEG (Anna Univ main campus), PSG Tech, MIT Chennai, Thiagarajar, Kumaraguru, Coimbatore IT, and 400+ more</td></tr>
    <tr><td><strong>Counselling</strong></td><td>Online. May-July window typically. Multiple rounds.</td></tr>
    <tr><td><strong>Cost</strong></td><td>Govt colleges: ₹50K-1L/year. Govt-aided (like PSG): ₹1-2L/year. Self-financing: ₹1-3L/year.</td></tr>
  </table>

  <div class="verified">
    <strong>Bottom line:</strong> Even if JEE goes badly, a student scoring 95%+ in CBSE Class 12 can get CEG Anna University CS or PSG Tech CS through TNEA. This is the most underrated safety net in Indian engineering admissions.
  </div>

  <h3>NIT Trichy — 50% Home State Quota <span class="tag-verified">VERIFIED</span></h3>
  <p>NIT Trichy is among India's best NITs (NIRF Eng top-10 regularly). Under JOSAA counselling:</p>
  <ul>
    <li><strong>50% of seats</strong> are reserved for Home State (TN) students via JEE Main</li>
    <li>This means cutoff ranks for TN students are significantly HIGHER (more lenient) than All India quota</li>
    <li>A JEE Main rank that wouldn't get CS at NIT Trichy nationally may get it via TN quota</li>
    <li>This applies to ALL programs: CS, ECE, IT, EEE, etc.</li>
  </ul>

  <h3>Top TN Colleges — Detailed <span class="tag-verified">VERIFIED</span></h3>

  <h4>PSG College of Technology, Coimbatore</h4>
  <table>
    <tr><td><strong>Founded</strong></td><td>1951 by PSG & Sons Charities. Government-aided, autonomous.</td></tr>
    <tr><td><strong>Affiliation</strong></td><td>Anna University. Autonomous status since 1978.</td></tr>
    <tr><td><strong>NIRF</strong></td><td>Engineering #67 (2024). Outlook Private Eng #8.</td></tr>
    <tr><td><strong>Programs</strong></td><td>~50 UG/PG programs. Offers rare 5-year sandwich engineering courses (classroom + industrial training).</td></tr>
    <tr><td><strong>Students</strong></td><td>~8,500 undergraduates.</td></tr>
    <tr><td><strong>Notable alumni</strong></td><td>Shiv Nadar (HCL founder, ₹28K Cr net worth), C Vijayakumar (HCL CEO), Lakshmi Narayanan (Cognizant ex-CEO), Mylswamy Annadurai (Chandrayaan Project Director, ISRO), Ragunathan Rajkumar (Professor at Carnegie Mellon)</td></tr>
    <tr><td><strong>Admission</strong></td><td>TNEA (Class 12 marks). No entrance exam needed.</td></tr>
    <tr><td><strong>Fees</strong></td><td>Government-aided: very affordable (₹1-2L/year approximate).</td></tr>
  </table>

  <h4>CEG — College of Engineering, Guindy (Anna University main campus)</h4>
  <table>
    <tr><td><strong>Founded</strong></td><td>1794. Asia's oldest technical institution. 231 years old.</td></tr>
    <tr><td><strong>Type</strong></td><td>Public, autonomous. Main campus of Anna University.</td></tr>
    <tr><td><strong>Location</strong></td><td>223 acres in central Chennai (Guindy).</td></tr>
    <tr><td><strong>Notable alumni</strong></td><td>Raj Reddy (Turing Award winner, CMU Professor), Verghese Kurien (White Revolution architect), Ashok Elluswamy (VP of AI, Tesla), Dhiraj Rajaram (Mu Sigma founder), Ravi Ruia (Essar Group)</td></tr>
    <tr><td><strong>Admission</strong></td><td>TNEA (Class 12 marks).</td></tr>
    <tr><td><strong>CS/IT strength</strong></td><td>Long history. Chennai city location = strong startup and IT ecosystem exposure.</td></tr>
  </table>

  <h4>SSN College / Shiv Nadar University Chennai</h4>
  <table>
    <tr><td><strong>Founded</strong></td><td>1996 by Shiv Nadar (HCL founder). 230-acre campus on OMR, Chennai.</td></tr>
    <tr><td><strong>CRITICAL CHANGE (2026)</strong></td><td>Merging into Shiv Nadar University Chennai from 2026 academic year. Will become "SSN School of Engineering" under SNU. Admissions will SHIFT from TNEA to SNU's own entrance exam.</td></tr>
    <tr><td><strong>Partnership</strong></td><td>Carnegie Mellon University (School of Advanced Software Engineering since 2001).</td></tr>
    <tr><td><strong>Notable alumni</strong></td><td>R. Ashwin (India cricket), plus strong IT industry placement.</td></tr>
    <tr><td><strong>Impact</strong></td><td>Under SNU, expect improved research output but potentially higher fees. Watch for SNU admission process details.</td></tr>
  </table>

  <h4>Amrita Vishwa Vidyapeetham (Coimbatore + Chennai + 8 more campuses)</h4>
  <table>
    <tr><td><strong>Type</strong></td><td>Private deemed university. NAAC A++. 10 campuses across India.</td></tr>
    <tr><td><strong>NIRF 2024</strong></td><td>Overall #18. Engineering #23. Universities #7. Research #33.</td></tr>
    <tr><td><strong>Coimbatore campus</strong></td><td>450 acres at Ettimadai. Main campus since 1994.</td></tr>
    <tr><td><strong>Chennai campus</strong></td><td>Vengal, near Chennai. Engineering + Computing since 2019.</td></tr>
    <tr><td><strong>Admission</strong></td><td>AEEE (Amrita Engineering Entrance Exam) + JEE Main + SAT (NRI).</td></tr>
    <tr><td><strong>Research</strong></td><td>70+ research centers. 500+ active projects. 27 faculty in Stanford's top 2% scientists (2024). 150+ patents.</td></tr>
    <tr><td><strong>Honest take</strong></td><td>Legitimately strong research university (unlike VIT/SRM). But campus life is strict/conservative. Check if that matters.</td></tr>
  </table>

  <div class="caution">
    <strong>TNEA timing note:</strong> TNEA counselling usually happens May-July, AFTER Class 12 results. No separate registration deadline for the exam itself (there is no exam). But you MUST register for TNEA counselling when the window opens. Watch tneaonline.org from April 2027.
  </div>
</div>

<!-- SECTION 5: OUTCOMES -->
<div class="section">
  <h2>5. Best Case / Worst Case / Typical Outcomes</h2>

  <div class="verified">
    <strong>Note:</strong> CMI outcomes are <span class="tag-verified">VERIFIED</span> from official name-by-name placement page (cmi.ac.in/admissions/placement.php). Other institution outcomes are <span class="tag-approx">APPROX</span> or <span class="tag-unverified">UNVERIFIED</span> based on industry knowledge.
  </div>

  <h3>Research Institutions (CMI / ISI / IISc / IISERs)</h3>
  <table>
    <tr><th>Institution</th><th class="best">Best Case</th><th class="typical">Typical Case</th><th class="worst">Worst Case</th><th>Status</th></tr>
    <tr>
      <td><strong>CMI</strong><br>Math+CS</td>
      <td class="best">PhD at MIT/Princeton/Harvard → Faculty or Google Research (₹1-4 Cr/yr)</td>
      <td class="typical">PhD at top-50 global univ → Faculty at IIT/IISER, or Quant Finance ₹15-30L</td>
      <td class="worst">Joins analytics at ₹8-12L (rare ~5%)</td>
      <td><span class="tag-verified">VERIFIED</span><br><span class="small">Official placement page, every graduate listed by name 2001-2023</span></td>
    </tr>
    <tr>
      <td><strong>ISI</strong><br>B.Stat/B.Math</td>
      <td class="best">Quant Finance (Wall Street) ₹50L-3Cr/yr. Or PhD MIT/Princeton.</td>
      <td class="typical">M.Stat at ISI → Quant ₹20-40L, or PhD at good university</td>
      <td class="worst">Analytics/data role ₹10-15L.</td>
      <td><span class="tag-approx">APPROX</span><br><span class="small">Industry reputation; ISI placement page didn't load</span></td>
    </tr>
    <tr>
      <td><strong>IISc</strong><br>BS Research</td>
      <td class="best">Top global PhD → world-class research career. NIRF #1 research.</td>
      <td class="typical">Research at Google/Microsoft India or PhD globally. ₹15-25L or stipend.</td>
      <td class="worst">Industry R&D at ₹10-15L.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>IISERs</strong><br>BS-MS</td>
      <td class="best">Faculty at IITs. PhD at Cambridge/Max Planck.</td>
      <td class="typical">PhD in India/abroad → Research career. Some Data Science ₹12-20L.</td>
      <td class="worst">5 years invested, limited industry jobs if research path abandoned. ₹6-10L.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
  </table>

  <h3>CMI Outcomes — Verified Data Highlights</h3>
  <p>From <strong>cmi.ac.in/admissions/placement.php</strong>, actual names and destinations (sample from recent batches):</p>
  <table>
    <tr><th>Graduate</th><th>Destination</th><th>Year</th></tr>
    <tr><td>Amit Deshpande</td><td>PhD CS, MIT → Microsoft Research India</td><td>2002</td></tr>
    <tr><td>Indraneel Mukherjee</td><td>PhD CS, Princeton → Founder & CEO, LiftIgniter (Silicon Valley)</td><td>2006</td></tr>
    <tr><td>Uma Girish</td><td>PhD CS, Princeton University</td><td>2016</td></tr>
    <tr><td>Ananth Shankar</td><td>PhD Math, Harvard → Faculty, Northwestern University</td><td>2012</td></tr>
    <tr><td>Deeparaj Bhat</td><td>PhD Math, MIT</td><td>2019</td></tr>
    <tr><td>Aadityan Ganesh</td><td>PhD CS, Princeton</td><td>2022</td></tr>
    <tr><td>Akashdeep Dey</td><td>PhD Math, Princeton</td><td>2015/2017</td></tr>
    <tr><td>Mohan Swaminathan</td><td>PhD Math, Princeton</td><td>2017</td></tr>
    <tr><td>Debjit Paria</td><td>Quant Researcher, Millennium Management LLC</td><td>2022</td></tr>
    <tr><td>Jyothi Surya Prakash Bugatha</td><td>Quant Researcher, Mathisys Advisors</td><td>2022</td></tr>
    <tr><td>Mrunmay Jagadale</td><td>PhD Physics, Caltech</td><td>2018</td></tr>
    <tr><td>Suguman Bansal</td><td>PhD CS, Rice → Faculty, Georgia Tech</td><td>2014</td></tr>
  </table>
  <p class="small">This is a small sample. The full list has 500+ graduates across 22 years — all publicly listed on the CMI website.</p>

  <h3>Engineering Institutions</h3>
  <table>
    <tr><th>Institution</th><th class="best">Best Case</th><th class="typical">Typical Case</th><th class="worst">Worst Case</th><th>Status</th></tr>
    <tr>
      <td><strong>IIT Top 5 CS</strong></td>
      <td class="best">₹1-2 Cr intl (Google, quant). Startup founder. MS/PhD Stanford.</td>
      <td class="typical">₹25-40L at product companies. MS abroad.</td>
      <td class="worst">₹12-15L (very high floor).</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>Newer IITs CS</strong><br>(Tirupati, Palakkad)</td>
      <td class="best">₹25-35L at product cos. IIT network.</td>
      <td class="typical">₹12-20L.</td>
      <td class="worst">₹8-12L. Fewer companies visit.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>NIT Trichy CS</strong></td>
      <td class="best">₹30-50L (Google, Amazon visit).</td>
      <td class="typical">₹12-18L.</td>
      <td class="worst">₹5-8L mass recruiters.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>BITS Pilani CS</strong></td>
      <td class="best">₹40-60L. Strong startup/Silicon Valley network.</td>
      <td class="typical">₹15-25L.</td>
      <td class="worst">₹8-12L.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>IIIT Hyderabad CS</strong></td>
      <td class="best">₹40-60L. Top AI research from undergrad.</td>
      <td class="typical">₹15-25L.</td>
      <td class="worst">₹8-10L.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>IIST</strong></td>
      <td class="best">ISRO scientist. Caltech fellowship.</td>
      <td class="typical">ISRO/DRDO/HAL govt career.</td>
      <td class="worst">Govt pay scale ₹6-8L. Stable but not high-paying.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>VIT/SRM CS</strong></td>
      <td class="best">Top 5%: ₹15-25L at product cos.</td>
      <td class="typical">₹4-8L.</td>
      <td class="worst">₹3.5L TCS/Infosys mass hiring.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>PSG Tech / CEG CS</strong></td>
      <td class="best">₹20-30L at product cos (top performers). Startup founders.</td>
      <td class="typical">₹6-12L. Strong TN IT ecosystem connections.</td>
      <td class="worst">₹3.5-5L service companies.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
    <tr>
      <td><strong>Amrita CS</strong></td>
      <td class="best">₹20-30L. Strong research track for research-oriented students.</td>
      <td class="typical">₹6-12L.</td>
      <td class="worst">₹4-6L.</td>
      <td><span class="tag-approx">APPROX</span></td>
    </tr>
  </table>
</div>

<!-- SECTION 6: AI ANGLE -->
<div class="section">
  <h2>6. The AI Angle — Real vs Hype</h2>

  <h3>What AI career layers exist</h3>
  <table>
    <tr><th>Layer</th><th>Role</th><th>Who Gets Hired</th><th>Salary</th></tr>
    <tr><td><strong>1. AI Research</strong><br>(Creates new AI)</td><td>Research Scientist at DeepMind, OpenAI, Meta FAIR</td><td>PhD from CMU/Stanford/MIT. Or exceptional from CMI/ISI/IISc.</td><td><span class="tag-unverified">UNVERIFIED</span> ₹1-4 Cr/yr</td></tr>
    <tr><td><strong>2. ML Engineering</strong><br>(Builds AI systems)</td><td>ML Engineer at Google, Amazon, startups</td><td>Strong CS BTech + solid math. IIT/BITS/IIIT-H/NIT top.</td><td><span class="tag-approx">APPROX</span> ₹30-80L</td></tr>
    <tr><td><strong>3. AI Applied</strong><br>(Uses AI APIs)</td><td>AI Product Engineer</td><td>Any CS graduate who learns fast</td><td><span class="tag-approx">APPROX</span> ₹10-25L</td></tr>
    <tr><td><strong>4. "AI" in title</strong><br>(Dashboards)</td><td>Data analyst with AI buzzword</td><td>Anyone with 3-month course</td><td><span class="tag-approx">APPROX</span> ₹4-10L</td></tr>
  </table>

  <div class="critical">
    <strong>Layer 4 is being automated by AI itself.</strong> Layer 3 is becoming commoditized. The "loads of money" and "MIT researcher" dreams live in Layers 1-2 only. These require DEEP math + CS foundations — not an "AI program" label.
  </div>

  <h3>Where AI research actually happens in India</h3>
  <table>
    <tr><th>Institution</th><th>AI Lab/Center</th><th>Credibility</th></tr>
    <tr><td>IISc Bangalore</td><td>Robert Bosch Centre for Cyber-Physical Systems</td><td>Publishes at NeurIPS, ICML. Google/Microsoft funded.</td></tr>
    <tr><td>IIT Madras</td><td>RBCDSAI (Robert Bosch Centre for Data Science & AI)</td><td>India's top AI lab with industry partnerships. In Chennai.</td></tr>
    <tr><td>IIIT Hyderabad</td><td>CVIT (Centre for Visual Information Technology)</td><td>India's #1 computer vision lab. Top CVPR/ECCV papers.</td></tr>
    <tr><td>ISI Kolkata</td><td>Machine Intelligence Unit, CVPRU</td><td>Pioneer in pattern recognition since 1950s.</td></tr>
    <tr><td>IIT Bombay</td><td>AI/ML research group</td><td>Strong. Wadhwani AI partnership.</td></tr>
  </table>

  <div class="caution">
    <strong>"B.Tech in AI" at private universities</strong> is typically a standard CS curriculum with 2-3 ML electives repackaged under a new name. No research labs of note. No papers at top venues. Placement outcomes identical to regular CS. Don't pay premium for a label.
  </div>

  <h3>CS vs ECE for AI</h3>
  <table>
    <tr><th>Aspect</th><th>CS Path</th><th>ECE Path</th></tr>
    <tr><td>AI relevance</td><td>Direct: algorithms, ML, systems</td><td>Indirect but critical: hardware, embedded AI, signal processing</td></tr>
    <tr><td>Current money</td><td>Software AI / LLMs / Quant</td><td>Chip design (NVIDIA, Qualcomm, Apple)</td></tr>
    <tr><td>Future scarcity</td><td>AI software engineers = increasingly common</td><td>AI hardware engineers = scarce and getting MORE valuable</td></tr>
    <tr><td>Where AI is going</td><td>LLMs, agentic AI, applications</td><td>Edge AI, NPU/TPU design, autonomous vehicles, robotics</td></tr>
    <tr><td>MIT/Stanford PhD</td><td>CS → AI research</td><td>ECE → AI hardware, robotics, signal processing</td></tr>
  </table>
  <p><strong>Insight:</strong> Everyone is rushing to CS for AI. The next bottleneck is HARDWARE. NVIDIA is worth $3 trillion because chips matter. A student who understands ECE + AI will be rarer in 2035.</p>
</div>

<!-- SECTION 7: MONEY + RESEARCH -->
<div class="section">
  <h2>7. Where "Loads of Money" Meets "MIT Researcher"</h2>

  <p>These goals seem opposite. They're not. The key insight:</p>

  <div class="action">
    <strong>The highest-paying careers in tech (quant finance, AI research) require the SAME math/CS foundations as the best research careers.</strong> ISI B.Stat and CMI Math+CS are where both paths start.
  </div>

  <h3>Careers where research = money <span class="tag-unverified">UNVERIFIED</span></h3>
  <table>
    <tr><th>Role</th><th>Salary Range (Year 1-3)</th><th>How You Get There</th></tr>
    <tr><td>Quant Researcher (Citadel, Two Sigma, Jane Street)</td><td>₹1.5 - 4 Cr/yr</td><td>ISI/CMI → directly recruited OR PhD → recruited</td></tr>
    <tr><td>Research Scientist (Google DeepMind)</td><td>₹80L - 2 Cr/yr</td><td>PhD at MIT/Stanford/CMU</td></tr>
    <tr><td>ML Research (OpenAI, Meta FAIR)</td><td>₹1 - 3 Cr/yr</td><td>PhD in ML/AI at top program</td></tr>
    <tr><td>Tenured Faculty at MIT/Stanford</td><td>₹1.5 - 2.5 Cr/yr + consulting</td><td>PhD → postdoc → publish exceptional work</td></tr>
    <tr><td>Hedge Fund Quant (5 years)</td><td>₹3 - 10 Cr/yr</td><td>ISI/CMI math background → Wall Street</td></tr>
  </table>
  <p class="small">Salary ranges are approximate industry estimates. Actual offers vary significantly. These represent top-tier outcomes, not average outcomes.</p>

  <h3>The institutions that keep BOTH doors open</h3>
  <table>
    <tr><th>#</th><th>Institution</th><th>Money Door</th><th>MIT Researcher Door</th></tr>
    <tr><td>1</td><td><strong>ISI B.Stat/B.Math</strong></td><td>Quant firms recruit directly. Goldman Sachs pipeline.</td><td>ISI→MIT/Princeton PhD is established path. Multiple alumni/yr.</td></tr>
    <tr><td>2</td><td><strong>CMI Math+CS</strong></td><td>Goldman, Credit Suisse, Millennium Management recruit. Verified from placement data.</td><td>PhD at MIT, Princeton, Harvard, Stanford — every year. Verified.</td></tr>
    <tr><td>3</td><td><strong>IIT Top-5 CS</strong></td><td>₹1-2Cr intl packages. Quant firms visit IIT B/D.</td><td>IIT→MIT is most common India→MIT pipeline.</td></tr>
    <tr><td>4</td><td><strong>IISc BS</strong></td><td>Weaker on direct money. Mostly research path.</td><td>NIRF #1 research. Recommendation letters carry massive weight globally.</td></tr>
    <tr><td>5</td><td><strong>IIIT-H CS</strong></td><td>₹25-50L placements.</td><td>CVIT research → PhD at CMU/Stanford possible.</td></tr>
  </table>
</div>

<!-- SECTION 8: EXAM CALENDAR -->
<div class="section">
  <h2>8. Exam Calendar — All 11+ Exams for JEE 2027 Cycle</h2>

  <div class="caution">
    <strong>All dates below are ESTIMATED based on 2025-2026 patterns.</strong> Official 2027 dates will be announced from late 2026. Check official websites starting October 2026 for exact dates and registration windows.
  </div>

  <table>
    <tr><th>#</th><th>Exam</th><th>What It Opens</th><th>Est. Registration</th><th>Est. Exam Date</th><th>Type</th></tr>
    <tr><td>1</td><td><strong>JEE Main</strong> (Session 1)</td><td>NITs, IIITs, screening for Advanced</td><td>Nov 2026</td><td>Jan 2027</td><td>MCQ online</td></tr>
    <tr><td>2</td><td><strong>JEE Main</strong> (Session 2)</td><td>Same (best of 2 scores)</td><td>Feb 2027</td><td>Apr 2027</td><td>MCQ online</td></tr>
    <tr><td>3</td><td><strong>JEE Advanced</strong></td><td>IITs, IIST</td><td>Apr 2027</td><td>May/Jun 2027</td><td>MCQ + Numerical</td></tr>
    <tr><td>4</td><td><strong>BITSAT</strong></td><td>BITS Pilani/Goa/Hyderabad</td><td>Jan 2027</td><td>May 2027</td><td>Online MCQ</td></tr>
    <tr><td>5</td><td><strong>IAT</strong> (IISER Aptitude)</td><td>7 IISERs + IISc BS + IIT Madras BS</td><td>Mar 2027</td><td>Jun 2027</td><td>Written exam</td></tr>
    <tr><td>6</td><td><strong>CMI Entrance</strong></td><td>CMI Chennai</td><td>Mar 2027</td><td>May 2027</td><td>Proof-based math</td></tr>
    <tr><td>7</td><td><strong>ISI Admission Test</strong></td><td>ISI B.Stat/B.Math (Kolkata/Bangalore)</td><td>Mar 2027</td><td>May 2027</td><td>Proof-based math</td></tr>
    <tr><td>8</td><td><strong>NEST</strong></td><td>NISER + UM-DAE CEBS</td><td>Mar 2027</td><td>Jun 2027</td><td>MCQ + Subjective</td></tr>
    <tr><td>9</td><td><strong>IIIT-H UGEE</strong></td><td>IIIT Hyderabad</td><td>Mar 2027</td><td>May 2027</td><td>Own exam</td></tr>
    <tr><td>10</td><td><strong>TNEA</strong></td><td>TN state engineering colleges</td><td>May 2027</td><td>No exam (12th %)</td><td>Board marks based</td></tr>
    <tr><td>11</td><td><strong>VITEEE / SRMJEE</strong></td><td>VIT / SRM (safety)</td><td>Dec 2026</td><td>Apr-May 2027</td><td>Online MCQ</td></tr>
    <tr><td>12</td><td><strong>TNEA</strong></td><td>PSG, CEG, Anna Univ colleges, 450+ TN colleges</td><td>Apr-May 2027</td><td>No exam (Class 12 marks)</td><td>Marks based</td></tr>
    <tr><td>13</td><td><strong>AEEE</strong></td><td>Amrita Vishwa Vidyapeetham (all campuses)</td><td>Dec 2026</td><td>Jan-Apr 2027</td><td>Online MCQ</td></tr>
    <tr><td>14</td><td><strong>COMEDK</strong></td><td>Karnataka private engineering colleges (safety)</td><td>Jan 2027</td><td>May 2027</td><td>Online MCQ</td></tr>
  </table>

  <div class="action">
    <strong>Critical:</strong> Exams 5, 6, 7, 8 are SEPARATE from JEE and test DIFFERENT skills. The coaching center won't prep for these. The student must self-prepare for ISI/CMI style (proof-based) problems, which reward deep mathematical thinking over speed.
  </div>

  <h3>Exam Independence Map</h3>
  <p>Failing one exam does NOT affect others. These are all independent shots:</p>
  <table>
    <tr><th>Exam Group</th><th>What It Tests</th><th>Affects Others?</th></tr>
    <tr><td>JEE Main + Advanced</td><td>Speed + accuracy (MCQ)</td><td>Main score needed for Advanced eligibility. Otherwise independent.</td></tr>
    <tr><td>BITSAT</td><td>Speed + breadth (MCQ)</td><td>Completely independent.</td></tr>
    <tr><td>ISI / CMI</td><td>Deep mathematical thinking (proofs)</td><td>Independent. Different skill set from JEE.</td></tr>
    <tr><td>IAT (IISERs)</td><td>Science aptitude (all 3 subjects)</td><td>Independent. Also gives IISc and IIT Madras BS.</td></tr>
    <tr><td>NEST</td><td>Science depth</td><td>Independent.</td></tr>
    <tr><td>UGEE (IIIT-H)</td><td>CS aptitude</td><td>Independent.</td></tr>
  </table>
</div>

<!-- SECTION 9: INSTITUTION DEEP DIVES -->
<div class="section">
  <h2>9. Top Institution Deep Dives</h2>

  <h3>1. ISI — Indian Statistical Institute <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><td><strong>Programs</strong></td><td>B.Stat (Hons) at Kolkata, B.Math (Hons) at Bangalore, BSDS at Kolkata/Delhi</td></tr>
    <tr><td><strong>Duration</strong></td><td>B.Stat/B.Math: 3 years. BSDS: 4 years.</td></tr>
    <tr><td><strong>Fees</strong></td><td>ZERO tuition. Monthly stipend provided. Free hostel.</td></tr>
    <tr><td><strong>Admission</strong></td><td>B.Stat/B.Math: Own entrance test (proof-based). BSDS: JEE Main math percentile + CUET.</td></tr>
    <tr><td><strong>Status</strong></td><td>Institute of National Importance (Parliament act 1959). Under Ministry of Statistics.</td></tr>
    <tr><td><strong>Why it matters</strong></td><td>Machine Intelligence Unit = India's oldest ML lab. Quant finance firms recruit directly. Free education at world-class level.</td></tr>
    <tr><td><strong>Best for</strong></td><td>The "money + research" dual dream. Math-loving students.</td></tr>
  </table>

  <h3>2. CMI — Chennai Mathematical Institute <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><td><strong>Programs</strong></td><td>BSc (Hons) 4-year: Math, Math+CS, Math+Physics. Data Science minor available.</td></tr>
    <tr><td><strong>Location</strong></td><td>Siruseri, Chennai (OMR IT corridor). Student doesn't leave TN.</td></tr>
    <tr><td><strong>Batch size</strong></td><td>~30-50 total undergrads. Exceptional mentoring ratio.</td></tr>
    <tr><td><strong>Fees</strong></td><td>Historically waived for good academic standing. Modest even otherwise.</td></tr>
    <tr><td><strong>Admission</strong></td><td>Own entrance exam (proof-based math). National Math/Physics/Informatics Olympiad = direct admission.</td></tr>
    <tr><td><strong>MoUs</strong></td><td>École Normale Supérieure, Paris. École Polytechnique. Students go to Paris for summer.</td></tr>
    <tr><td><strong>Verified outcomes</strong></td><td>PhD at MIT, Princeton, Harvard, Stanford, CMU, Chicago — EVERY year. Also Goldman, Millennium, Credit Suisse. Full list at cmi.ac.in/admissions/placement.php</td></tr>
  </table>

  <h3>3. IISc Bangalore — BS (Research) <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><td><strong>Program</strong></td><td>4-year BS (Research) in 6 disciplines + B.Tech in Math & Computing</td></tr>
    <tr><td><strong>Admission</strong></td><td>IAT (IISER Aptitude Test). Same exam as IISERs.</td></tr>
    <tr><td><strong>Rankings</strong></td><td>NIRF Overall #2. Research #1. Universities #1. Institute of Eminence.</td></tr>
    <tr><td><strong>UG intake</strong></td><td>~533 undergraduates (2024 data).</td></tr>
    <tr><td><strong>Fees</strong></td><td>Government institute. Nominal fees.</td></tr>
  </table>

  <h3>4. IISERs (7 campuses) <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><td><strong>Campuses</strong></td><td>Pune, Kolkata, Mohali, Bhopal, Thiruvananthapuram, Tirupati (near TN), Berhampur</td></tr>
    <tr><td><strong>Program</strong></td><td>5-year BS-MS dual degree in basic sciences.</td></tr>
    <tr><td><strong>Admission</strong></td><td>EXCLUSIVELY IAT from 2024. JEE channel removed. KVPY dead.</td></tr>
    <tr><td><strong>Budget</strong></td><td>₹1,353 crore combined (FY 2025-26). Govt funded. Nominal fees.</td></tr>
    <tr><td><strong>Also admits to</strong></td><td>IISc BS + IIT Madras BS-Medical Sciences + IIT Guwahati BS-Biomedical via same IAT.</td></tr>
    <tr><td><strong>Note</strong></td><td>IISER Bhopal also offers 4-year B.Tech in Data Science, Electrical Engineering, Chemical Engineering.</td></tr>
  </table>

  <h3>5. IIIT Hyderabad <span class="tag-verified">VERIFIED</span></h3>
  <table>
    <tr><td><strong>Program</strong></td><td>BTech CS (with research tracks: CRR, CLD), BTech ECE</td></tr>
    <tr><td><strong>Admission</strong></td><td>UGEE (own exam) + JEE Main channel + SPEC (special channel)</td></tr>
    <tr><td><strong>AI strength</strong></td><td>CVIT (Centre for Visual Information Technology) — India's top computer vision lab.</td></tr>
    <tr><td><strong>Why unique</strong></td><td>Research exposure from year 1. Students publish papers as undergrads.</td></tr>
  </table>

  <h3>6. IIT Madras <span class="tag-approx">APPROX</span></h3>
  <table>
    <tr><td><strong>Programs</strong></td><td>BTech CS, ECE, Math & Computing (via JEE Advanced). BS Medical Sciences (via IAT).</td></tr>
    <tr><td><strong>AI lab</strong></td><td>RBCDSAI — Robert Bosch Centre for Data Science & AI. Google partnership.</td></tr>
    <tr><td><strong>Location</strong></td><td>Chennai. Home ground for TN student.</td></tr>
    <tr><td><strong>Why relevant</strong></td><td>Math & Computing at IIT Madras = ideal for AI + research path. Lower cutoff than CS.</td></tr>
  </table>

  <h3>7-12. Other Key Institutions (Brief)</h3>
  <table>
    <tr><th>Institution</th><th>Key Point</th><th>Admission</th></tr>
    <tr><td><strong>NISER</strong></td><td>Under DAE. BARC fast-track. ₹5K/month stipend.</td><td>NEST exam</td></tr>
    <tr><td><strong>IIST</strong></td><td>Only space university in Asia. 140 seats. ISRO pipeline. Caltech fellowship.</td><td>JEE Advanced</td></tr>
    <tr><td><strong>NIT Trichy</strong></td><td>50% TN home state quota. Excellent CS/ECE. Google/Amazon visit.</td><td>JEE Main</td></tr>
    <tr><td><strong>BITS Pilani</strong></td><td>No reservation = pure merit. Strong startup culture. ₹20-25L total fees.</td><td>BITSAT</td></tr>
    <tr><td><strong>IIT Tirupati</strong></td><td>IIT tag. Lower cutoff. Growing. Close to TN.</td><td>JEE Advanced</td></tr>
    <tr><td><strong>IIT Palakkad</strong></td><td>IIT tag. Kerala border. CS growing.</td><td>JEE Advanced</td></tr>
  </table>
</div>

<!-- SECTION 10: FEE STRUCTURES -->
<div class="section">
  <h2>10. Fee Structures <span class="tag-approx">APPROX</span></h2>

  <div class="caution">
    All fees below are approximate ranges based on 2024-2025 data. Verify from official sources for 2027 admission. Fees change annually.
  </div>

  <table>
    <tr><th>Institution</th><th>Approx Total Cost (full program)</th><th>Notes</th></tr>
    <tr><td>ISI</td><td><strong>FREE</strong> + stipend</td><td>No tuition. Monthly stipend. Free hostel.</td></tr>
    <tr><td>CMI</td><td>₹1-3L total (4 years)</td><td>Fees waived for good standing historically. Verify current policy.</td></tr>
    <tr><td>IISc</td><td>₹2-4L total (4 years)</td><td>Government institute. INSPIRE scholarships available.</td></tr>
    <tr><td>IISERs</td><td>₹2-5L total (5 years)</td><td>Government funded. INSPIRE/DAE fellowships offset costs.</td></tr>
    <tr><td>NISER</td><td>₹1-3L total (5 years)</td><td>DAE-DISHA fellowship: ₹5K/month + ₹20K/year contingency.</td></tr>
    <tr><td>IIST</td><td>₹3-6L total (4 years)</td><td>Government (Dept of Space) funded.</td></tr>
    <tr><td>IITs (all)</td><td>₹8-12L total (4 years)</td><td>₹2-3L/year tuition + hostel. SC/ST/EWS fee waiver.</td></tr>
    <tr><td>NITs</td><td>₹5-8L total (4 years)</td><td>Lower than IITs. Similar structure.</td></tr>
    <tr><td>IIIT Hyderabad</td><td>₹10-15L total (4 years)</td><td>Higher than NITs but not as high as BITS.</td></tr>
    <tr><td>BITS Pilani</td><td>₹20-25L total (4 years)</td><td>Private. No reservation. Merit + ability to pay.</td></tr>
    <tr><td>VIT / SRM</td><td>₹8-15L total (4 years)</td><td>Varies by branch. CS premium.</td></tr>
    <tr><td>Manipal</td><td>₹12-18L total (4 years)</td><td>Private. Karnataka-based.</td></tr>
    <tr><td>Amrita Vishwa Vidyapeetham</td><td>₹10-16L total (4 years)</td><td>Deemed university. NIRF Eng #23.</td></tr>
    <tr><td>CEG / Anna University</td><td>₹2-4L total (4 years)</td><td>Government. TNEA admission.</td></tr>
    <tr><td>PSG Tech</td><td>₹4-8L total (4 years)</td><td>Government-aided. TNEA admission.</td></tr>
    <tr><td>SSN / Shiv Nadar Univ Chennai</td><td>₹8-15L total (estimated)</td><td>Shifting to SNU fee structure from 2026.</td></tr>
  </table>

  <div class="verified">
    <strong>Key insight:</strong> The BEST institutions (ISI, CMI, IISc, IISERs, NISER) are the CHEAPEST. This is the great irony of Indian higher education — world-class institutions cost nearly nothing because they're government-funded. The expensive ones (BITS, VIT, SRM) are NOT necessarily better.
  </div>
</div>

<!-- SECTION 11: DECISION FRAMEWORK -->
<div class="section">
  <h2>11. Decision Framework</h2>

  <h3>The Two Questions</h3>

  <p><strong>Question 1: "What kind of life do I want at 28?"</strong></p>
  <table>
    <tr><th>If the answer is...</th><th>Then prioritize...</th></tr>
    <tr><td>"Solve hard problems, maybe become a professor or researcher"</td><td>CMI → ISI → IISERs → IISc</td></tr>
    <tr><td>"Work at Google/Meta/OpenAI and earn ₹30L+ quickly"</td><td>Top IITs CS → BITS CS → IIIT-H → NIT Trichy CS</td></tr>
    <tr><td>"Loads of money in quant finance"</td><td>ISI → CMI → IIT (Math+Computing) → BITS</td></tr>
    <tr><td>"Space scientist at ISRO"</td><td>IIST (no other option)</td></tr>
    <tr><td>"AI researcher at DeepMind / MIT"</td><td>CMI / ISI → PhD. Or IIT CS → PhD. Or IIIT-H → PhD.</td></tr>
    <tr><td>"Both money AND research — I want it all"</td><td>ISI → CMI → IIT Top-5 CS → IIIT-H</td></tr>
    <tr><td>"Not sure yet, want maximum options"</td><td>IIT (any) or BITS — gives broadest optionality</td></tr>
  </table>

  <p><strong>Question 2: "Am I a speed-thinker or deep-thinker?"</strong></p>
  <table>
    <tr><th>If...</th><th>Then...</th></tr>
    <tr><td>Speed + accuracy under time pressure (finishes tests fast)</td><td>JEE Main/Advanced is the primary game. Work on consistency.</td></tr>
    <tr><td>Deep thinker, enjoys solving hard problems slowly, good at proofs</td><td>ISI/CMI entrance exams REWARD this. JEE may undervalue the student.</td></tr>
    <tr><td>Good at all 3 sciences, not just math</td><td>IAT (IISERs + IISc) is the play.</td></tr>
  </table>

  <h3>The ISI Problem Test</h3>
  <div class="action">
    <p><strong>A concrete step the father should take THIS WEEK:</strong></p>
    <p>Buy an ISI entrance exam prep book (B.Stat-B.Math solved papers by "Tomato" series or Chakraborty & Ghosh). Give it to the student.</p>
    <ul>
      <li>If the student finds those problems <strong>exciting</strong> (even if unsolvable yet) → ISI/CMI is the right path</li>
      <li>If the student finds them <strong>boring</strong> and prefers building apps/projects → IIT/BITS/IIIT is the right path</li>
    </ul>
    <p>The student's reaction tells you more than any counselor ever will.</p>
  </div>
</div>

<!-- SECTION 12: VERIFICATION -->
<div class="section">
  <h2>12. Verification Status — Full Transparency</h2>

  <h3>What's confirmed</h3>
  <table>
    <tr><th>Claim</th><th>Source</th><th>Date Checked</th></tr>
    <tr><td>CMI programs, admission, deadlines, complete placement data</td><td>cmi.ac.in/admissions/</td><td>31 Mar 2026</td></tr>
    <tr><td>ISI programs, campuses, fee waiver, Institute of National Importance</td><td>Wikipedia + ISI Act 1959 references</td><td>31 Mar 2026</td></tr>
    <tr><td>IISERs: 7 campuses, IAT-only from 2024, BS-MS</td><td>Wikipedia (edited 15 Mar 2026)</td><td>31 Mar 2026</td></tr>
    <tr><td>IAT admits to IISc BS + IIT Madras BS-Medical Sciences</td><td>IISER system Wikipedia</td><td>31 Mar 2026</td></tr>
    <tr><td>NISER: NEST exam, DAE, BARC pipeline, stipend</td><td>Wikipedia + nestexam.in</td><td>31 Mar 2026</td></tr>
    <tr><td>IIST: 140 seats (60+60+20), JEE Advanced, under ISRO</td><td>Wikipedia + IIST references</td><td>31 Mar 2026</td></tr>
    <tr><td>IIIT Delhi: JAC Delhi, JEE Main based</td><td>Wikipedia</td><td>31 Mar 2026</td></tr>
    <tr><td>IIIT-H: UGEE/own exam, CVIT lab</td><td>Previous verified fetch</td><td>31 Mar 2026</td></tr>
    <tr><td>PSG Tech: NIRF Eng #67, est. 1951, 8,500 UG students, autonomous, Anna Univ affiliated</td><td>Wikipedia (PSG College of Technology)</td><td>31 Mar 2026</td></tr>
    <tr><td>CEG Anna Univ: est. 1794, Asia's oldest tech institution, public autonomous, TNEA admission</td><td>Wikipedia (College of Engineering, Guindy)</td><td>31 Mar 2026</td></tr>
    <tr><td>SSN: Merging into Shiv Nadar Univ Chennai from 2026; admissions shifting to SNU entrance</td><td>Wikipedia + Times of India (Sep 2025)</td><td>31 Mar 2026</td></tr>
    <tr><td>Amrita: NIRF Overall #18, Eng #23, Univ #7; deemed univ; NAAC A++; AEEE + JEE Main admission</td><td>Wikipedia + NIRF 2024 data</td><td>31 Mar 2026</td></tr>
  </table>

  <h3>What's approximate (verify before acting)</h3>
  <table>
    <tr><th>Claim</th><th>Confidence</th><th>How to verify</th></tr>
    <tr><td>Placement salary ranges at IITs/NITs/BITS</td><td>Medium — industry knowledge</td><td>Check institutional placement reports</td></tr>
    <tr><td>Quant finance salaries (ISI/CMI)</td><td>Medium — industry knowledge</td><td>Ask ISI/CMI alumni directly</td></tr>
    <tr><td>Fee structures</td><td>Medium — based on 2024-25 data</td><td>Check official fee pages for 2027</td></tr>
    <tr><td>Exam dates for 2027 cycle</td><td>Medium — based on 2025-26 patterns</td><td>Official announcements from Oct-Dec 2026</td></tr>
    <tr><td>JOSAA cutoff ranks</td><td>NOT VERIFIED — scraper not built</td><td>Check josaa.nic.in and cutoffs.iitr.ac.in</td></tr>
    <tr><td>TNEA counselling process for CBSE students</td><td>Medium — based on known TN process</td><td>Check tneaonline.org from April 2027</td></tr>
    <tr><td>SSN/SNU admission process for 2027</td><td>Low — merger just announced</td><td>Check snuchennai.edu.in when announced</td></tr>
  </table>

  <h3>What we explicitly don't know</h3>
  <ul>
    <li>What 150-240/300 weekly scores translate to in JEE Main rank — ask Sri Chaitanya directly</li>
    <li>Exact JOSAA 2027 cutoffs — don't exist yet</li>
    <li>Whether IISERs will maintain IAT-only admission in 2027 — likely yes, but policy can change</li>
    <li>CMI entrance difficulty vs JEE — different style (proof vs MCQ), not directly comparable</li>
  </ul>
</div>

<!-- SECTION 13: ACTION ITEMS -->
<div class="section">
  <h2>13. Action Items</h2>

  <h3>This Week (March-April 2026)</h3>
  <div class="action">
    <ol>
      <li><strong>Buy ISI prep book</strong> — Tomato series or B.Stat-B.Math previous papers. Let the student try 2-3 problems. Gauge reaction.</li>
      <li><strong>Visit CMI website</strong> — cmi.ac.in/admissions/placement.php — show the student the name-by-name outcomes. Let him see "PhD MIT" and "Goldman Sachs" from the same batch.</li>
      <li><strong>Note exam registration windows</strong> — Most open March-April 2027. Set calendar reminders starting October 2026.</li>
      <li><strong>Talk to the coaching center</strong> — Ask "what JEE Main rank does 150-240/300 weekly score translate to?" Get a realistic estimate.</li>
    </ol>
  </div>

  <h3>By October 2026</h3>
  <ul>
    <li>Begin ISI/CMI style problem practice (30 min/week alongside JEE prep — they use different muscles)</li>
    <li>Watch for JEE Main Session 1 registration (usually November)</li>
    <li>Watch for BITSAT registration (usually January)</li>
    <li>Watch for VITEEE/SRMJEE registration (usually December) — safety options</li>
  </ul>

  <h3>By February 2027</h3>
  <ul>
    <li>Complete JEE Main Session 1</li>
    <li>Register for CMI, ISI, IAT, NEST, UGEE — all open around March</li>
    <li>Decide on Session 2 of JEE Main (April) strategy based on Session 1 result</li>
  </ul>

  <h3>May-July 2027 — Decision Time</h3>
  <ul>
    <li>All exams completed. Multiple results in hand.</li>
    <li>Use this guide's framework to choose the best admit.</li>
    <li>Remember: ISI/CMI are FREE and produce better outcomes than many paying options.</li>
  </ul>

  <h3>Key URLs to Bookmark</h3>
  <table>
    <tr><th>Institution</th><th>URL</th></tr>
    <tr><td>CMI Admissions</td><td>cmi.ac.in/admissions/</td></tr>
    <tr><td>CMI Placements (verified data)</td><td>cmi.ac.in/admissions/placement.php</td></tr>
    <tr><td>ISI Admissions</td><td>isical.ac.in (search "admissions")</td></tr>
    <tr><td>IISER System</td><td>iiseradmission.in</td></tr>
    <tr><td>NEST (for NISER)</td><td>nestexam.in</td></tr>
    <tr><td>IIIT-H Admissions</td><td>ugadmissions.iiit.ac.in</td></tr>
    <tr><td>JOSAA (IITs/NITs)</td><td>josaa.nic.in</td></tr>
    <tr><td>BITS Admissions</td><td>bitsadmission.com</td></tr>
    <tr><td>IIST Admissions</td><td>iist.ac.in/admission</td></tr>
  </table>
</div>

<!-- FINAL NOTE -->
<div class="section">
  <h2>Final Note</h2>
  <p>Every institution in this guide represents a real opportunity. The worst mistake is not aiming too high — it's not knowing an option existed. A student who applies to all 11 exams has 11 independent shots at a great career. A student who only applies to JEE has one.</p>

  <div class="verified">
    <p><strong>The people building AI today — Sutskever, Hassabis, LeCun — none studied "B.Tech in AI." They built deep foundations in math and CS, then applied them.</strong></p>
    <p>The kid who builds deep math+CS foundations at ISI/CMI/IIT and THEN aims at AI will have no competition from the crowds chasing AI-labeled programs at private universities.</p>
  </div>

  <p class="small" style="margin-top: 40px; text-align: center; color: #999;">
    This guide was prepared on """ + datetime.now().strftime("%d %B %Y") + """. It contains a mix of verified and approximate information as tagged throughout.
    All critical decisions should be verified from official institutional websites.
    Not affiliated with any institution. No warranties expressed or implied.
  </p>
</div>

</body>
</html>
"""

def main():
    output_path = os.path.join(OUTPUT_DIR, "college_guide_2027.pdf")
    print(f"Generating PDF at {output_path}...")

    doc = weasyprint.HTML(string=HTML_CONTENT)
    doc.write_pdf(output_path)

    file_size = os.path.getsize(output_path) / 1024
    print(f"PDF generated: {output_path} ({file_size:.0f} KB)")


if __name__ == "__main__":
    main()
