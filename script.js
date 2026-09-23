const BACKEND_URL = "https://gig-lenn.onrender.com";

document.addEventListener("DOMContentLoaded", () => {
    const checkerForm = document.getElementById("checker-form");

    if (checkerForm) {
        checkerForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const linkInput = document.getElementById("job-link");
            const detailsInput = document.getElementById("opportunity-details");

            const link = linkInput ? linkInput.value.trim() : "";
            const details = detailsInput ? detailsInput.value.trim() : "";

            if (!link && !details) {
                showResult({
                    level: "CAUTION",
                    score: 0,
                    message: "Please enter a job link or opportunity details.",
                    explanation: "GigLenn needs information about the opportunity before it can check for warning signs.",
                    action: "Enter the job description, message, or website link and scan again.",
                    signals: []
                });
                return;
            }

            showLoading();

            try {
                let analysis = null;

                if (details) {
                    const response = await fetch(
                        `${BACKEND_URL}/analyze?text=${encodeURIComponent(details)}`
                    );

                    if (!response.ok) {
                        throw new Error("Backend analysis failed.");
                    }

                    analysis = await response.json();
                }

                if (link) {
                    const response = await fetch(
                        `${BACKEND_URL}/check?url=${encodeURIComponent(link)}`
                    );

                    if (!response.ok) {
                        throw new Error("Website check failed.");
                    }

                    const websiteResult = await response.json();

                    if (!analysis) {
                        analysis = websiteResult;
                    } else {
                        analysis = combineResults(analysis, websiteResult);
                    }
                }

                if (analysis) {
                    showResult(analysis);
                } else {
                    throw new Error("No analysis result received.");
                }

            } catch (error) {
                console.error(error);

                showResult({
                    level: "CAUTION",
                    score: 0,
                    message: "GigLenn could not complete the scan.",
                    explanation: "The GigLenn backend could not complete the requested check.",
                    action: "Please check your internet connection and try the scan again.",
                    signals: []
                });
            }
        });
    }

    setupReportForm();
});


function showLoading() {
    const resultBox = document.getElementById("result-box");

    if (!resultBox) return;

    resultBox.style.display = "block";

    resultBox.innerHTML = `
        <div class="result-header">
            <div class="result-label">SCANNING...</div>
            <div class="result-score">...</div>
        </div>

        <p class="result-message">
            GigLenn is checking this opportunity for warning signs.
        </p>
    `;

    resultBox.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function showResult(data) {
    const resultBox = document.getElementById("result-box");

    if (!resultBox) return;

    const level = data.risk?.level || data.level || "CAUTION";
    const score = Number(data.analysis?.score ?? data.score ?? 0);

    const message =
        data.risk?.message ||
        data.message ||
        "GigLenn has completed the scan.";

    const explanation =
        data.risk?.explanation ||
        data.explanation ||
        "";

    const action =
        data.risk?.action ||
        data.action ||
        "";

    const signals =
        data.analysis?.signals ||
        data.signals ||
        [];

    resultBox.style.display = "block";

    resultBox.innerHTML = `
        <div class="result-header">
            <div class="result-label">${escapeHTML(level)}</div>
            <div class="result-score">${score}/100</div>
        </div>

        <p class="result-message">
            ${escapeHTML(message)}
        </p>

        ${
            explanation
                ? `
                <div class="result-explanation">
                    <strong>Why:</strong>
                    ${escapeHTML(explanation)}
                </div>
                `
                : ""
        }

        ${
            action
                ? `
                <div class="recommended-action">
                    <strong>Recommended action:</strong>
                    ${escapeHTML(action)}
                </div>
                `
                : ""
        }

        ${
            signals.length
                ? `
                <div class="result-signals">
                    ${signals
                        .map(signal => `
                            <div class="signal-card">
                                <div class="signal-card-title">
                                    ${escapeHTML(
                                        signal.title ||
                                        signal.type ||
                                        "Warning sign"
                                    )}
                                </div>

                                <div class="signal-card-detail">
                                    ${escapeHTML(signal.detail || "")}
                                </div>
                            </div>
                        `)
                        .join("")}
                </div>
                `
                : `
                <div class="result-signals">
                    <div class="signal-card">
                        <div class="signal-card-title">
                            No specific warning signs detected
                        </div>

                        <div class="signal-card-detail">
                            This does not guarantee that the opportunity is legitimate. Continue to verify the employer independently.
                        </div>
                    </div>
                </div>
                `
        }
    `;

    resultBox.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}


function combineResults(first, second) {
    const firstScore =
        Number(first.analysis?.score ?? first.score ?? 0);

    const secondScore =
        Number(second.analysis?.score ?? second.score ?? 0);

    const signals = [
        ...(first.analysis?.signals || first.signals || []),
        ...(second.analysis?.signals || second.signals || [])
    ];

    const uniqueSignals = [];
    const seen = new Set();

    signals.forEach(signal => {
        const key =
            signal.title ||
            signal.type ||
            signal.detail;

        if (!seen.has(key)) {
            seen.add(key);
            uniqueSignals.push(signal);
        }
    });

    const score =
        Math.min(100, Math.max(firstScore, secondScore));

    let level = "NO OBVIOUS WARNING SIGNS";

    if (score >= 60) {
        level = "HIGH RISK";
    } else if (score >= 25) {
        level = "CAUTION";
    }

    return {
        level,
        score,

        message:
            level === "HIGH RISK"
                ? "This opportunity contains several warning signs that deserve serious caution."
                : level === "CAUTION"
                    ? "This opportunity contains some warning signs that should be checked carefully."
                    : "GigLenn did not find major warning patterns in the information provided.",

        explanation:
            uniqueSignals.length
                ? `GigLenn identified ${uniqueSignals.length} warning pattern${uniqueSignals.length === 1 ? "" : "s"}.`
                : "No major warning patterns were detected.",

        action:
            level === "HIGH RISK"
                ? "Stop and independently verify the employer, website, payment request, and contact details before proceeding."
                : level === "CAUTION"
                    ? "Pause before applying, paying, or sharing sensitive information. Verify the opportunity using independent sources."
                    : "You may continue researching the opportunity, but independently verify the employer before sharing money or sensitive information.",

        signals: uniqueSignals
    };
}


function setupReportForm() {
    const reportForm = document.getElementById("report-form");

    if (!reportForm) return;

    reportForm.addEventListener("submit", async function (event) {
        event.preventDefault();

        const data = {
            title: getValue("report-company"),
            url: getValue("report-link"),
            description: getValue("report-details"),
            payment: getValue("report-payment"),
            reason: getValue("report-source")
        };

        try {
            const response = await fetch(
                `${BACKEND_URL}/reports`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(data)
                }
            );

            if (!response.ok) {
                throw new Error("Report submission failed.");
            }

            const success =
                document.getElementById("report-success");

            if (success) {
                success.style.display = "block";

                success.textContent =
                    "Thank you. Your report has been submitted for review.";
            }

            reportForm.reset();

        } catch (error) {
            console.error(error);

            alert(
                "The report could not be submitted. Please try again."
            );
        }
    });
}


function getValue(id) {
    const element = document.getElementById(id);

    return element
        ? element.value.trim()
        : "";
}


function escapeHTML(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}