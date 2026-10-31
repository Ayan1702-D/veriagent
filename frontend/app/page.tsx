import { ClaimForm } from "@/components/ClaimForm";

const PROTOCOL = [
  ["01", "Frame", "Split broad language into claims that can actually be tested."],
  ["02", "Retrieve", "Collect independent sources and preserve a local snapshot."],
  ["03", "Contest", "Search deliberately for exceptions and counter-evidence."],
  ["04", "Rule", "Issue a calibrated verdict with limitations attached."],
];

export default function Home() {
  return (
    <main id="main-content" className="home-main">
      <aside className="docket-rail" aria-hidden="true">
        <span>VA / CLAIM EXAMINATION</span><b>2026—</b>
      </aside>
      <div className="intake-sheet">
        <header className="intake-heading">
          <div className="document-meta">
            <span>Document VA–01</span><span>Revision 07</span><span>Open access</span>
          </div>
          <div className="intake-title">
            <p>Independent verification<br />with an inspectable record.</p>
            <h1>Submit a claim<br />for examination.</h1>
            <span className="folio" aria-hidden="true">01</span>
          </div>
          <div className="intake-instruction">
            <b>Before filing</b>
            <p>Write one factual statement. We will identify its scope, gather evidence, look for what disproves it, and retain every step.</p>
            <a href="#claim-intake">Proceed to field 01 ↓</a>
          </div>
        </header>

        <ClaimForm />

        <section className="protocol" aria-labelledby="protocol-title">
          <div className="protocol-heading">
            <span>Examination protocol</span>
            <h2 id="protocol-title">What happens to a filed claim</h2>
            <p>No answer is forced into true or false. Conditions and insufficient evidence remain visible.</p>
          </div>
          <ol>
            {PROTOCOL.map(([number, title, description]) => (
              <li key={number}><span>{number}</span><strong>{title}</strong><p>{description}</p></li>
            ))}
          </ol>
        </section>

        <footer className="intake-footnote">
          <span>* Quotes are matched against stored source text.</span>
          <span>* Repeated publications do not count as independent evidence.</span>
          <span>* Every run has a hard resource limit.</span>
        </footer>
      </div>
    </main>
  );
}
