```javascript
// =========================================
// GigLenn ADMIN
// =========================================

const ADMIN_USERNAME = "admin";
const ADMIN_PASSWORD = "GigLenn123";
const BACKEND_URL = "http://localhost:3000";


// =========================================
// PAGE LOAD
// =========================================

document.addEventListener("DOMContentLoaded", function () {

    const loginForm = document.getElementById("login-form");
    const loginScreen = document.getElementById("login-screen");
    const dashboard = document.getElementById("admin-dashboard");
    const loginError = document.getElementById("login-error");
    const logoutButton = document.getElementById("logout-button");

    if (loginError) {
        loginError.style.display = "none";
    }


    // =====================================
    // LOGIN
    // =====================================

    if (loginForm) {

        loginForm.addEventListener("submit", function (event) {

            event.preventDefault();

            const username =
                document.getElementById("username").value.trim();

            const password =
                document.getElementById("password").value;


            if (
                username === ADMIN_USERNAME &&
                password === ADMIN_PASSWORD
            ) {

                sessionStorage.setItem(
                    "GigLennAdminLoggedIn",
                    "true"
                );

                loginScreen.style.display = "none";
                dashboard.style.display = "block";

                loadReports();

            } else {

                if (loginError) {
                    loginError.style.display = "block";
                }

            }

        });

    }


    // =====================================
    // LOGOUT
    // =====================================

    if (logoutButton) {

        logoutButton.addEventListener("click", function (event) {

            event.preventDefault();

            sessionStorage.removeItem(
                "GigLennAdminLoggedIn"
            );

            dashboard.style.display = "none";
            loginScreen.style.display = "flex";

            if (loginForm) {
                loginForm.reset();
            }

            if (loginError) {
                loginError.style.display = "none";
            }

        });

    }


    // =====================================
    // EXISTING LOGIN
    // =====================================

    if (
        sessionStorage.getItem("GigLennAdminLoggedIn") === "true"
    ) {

        loginScreen.style.display = "none";
        dashboard.style.display = "block";

        loadReports();

    }

});


// =========================================
// LOAD REPORTS FROM BACKEND
// =========================================

async function loadReports() {

    const container =
        document.getElementById("reports-container");

    if (!container) {
        return;
    }


    container.innerHTML = `
        <div class="empty-reports">
            <h3>Loading reports...</h3>
            <p>Please wait.</p>
        </div>
    `;


    try {

        const response =
            await fetch(BACKEND_URL + "/reports");


        if (!response.ok) {
            throw new Error("Could not load reports.");
        }


        const data =
            await response.json();


        let reports = [];


        if (Array.isArray(data)) {
            reports = data;
        } else if (Array.isArray(data.reports)) {
            reports = data.reports;
        }


        renderReports(reports);


    } catch (error) {

        console.error("Load reports error:", error);


        container.innerHTML = `
            <div class="empty-reports">

                <div class="empty-icon">⚠️</div>

                <h3>Could not load reports</h3>

                <p>
                    Make sure the GigLenn backend is running.
                </p>

                <button
                    type="button"
                    onclick="loadReports()"
                    class="primary-button"
                >
                    Try Again
                </button>

            </div>
        `;

    }

}


// =========================================
// RENDER REPORTS
// =========================================

function renderReports(reports) {

    const container =
        document.getElementById("reports-container");


    if (!container) {
        return;
    }


    updateStatistics(reports);


    if (reports.length === 0) {

        container.innerHTML = `

            <div class="empty-reports">

                <div class="empty-icon">📭</div>

                <h3>No reports yet</h3>

                <p>
                    When users submit reports,
                    they will appear here.
                </p>

                <a href="index.html#report">
                    Submit a test report →
                </a>

            </div>

        `;

        return;

    }


    container.innerHTML = "";


    reports.forEach(function (report) {

        const card =
            document.createElement("div");

        card.className =
            "admin-report-card";


        const payment =
            report.payment ||
            report.payment_requested ||
            "Not provided";


        const paymentClass =
            payment === "Yes"
                ? "payment-yes"
                : "payment-no";


        const status =
            report.status ||
            "pending";


        const date =
            report.created_at ||
            report.date ||
            report.submitted_at;


        const formattedDate =
            date
                ? new Date(date).toLocaleString()
                : "Unknown";


        const statusLabel =
            formatStatus(status);


        card.innerHTML = `

            <div class="report-top">

                <div>

                    <span class="report-label">
                        Opportunity
                    </span>

                    <h3>
                        ${escapeHTML(
                            report.company ||
                            "Unnamed opportunity"
                        )}
                    </h3>

                </div>


                <span class="report-status status-${escapeAttribute(status)}">
                    ${escapeHTML(statusLabel)}
                </span>

            </div>


            <div class="report-details-grid">

                <div>

                    <span class="detail-label">
                        Source
                    </span>

                    <strong>
                        ${escapeHTML(
                            report.source ||
                            "Not provided"
                        )}
                    </strong>

                </div>


                <div>

                    <span class="detail-label">
                        Asked for Money
                    </span>

                    <strong class="${paymentClass}">
                        ${escapeHTML(payment)}
                    </strong>

                </div>


                <div>

                    <span class="detail-label">
                        Amount
                    </span>

                    <strong>
                        ${escapeHTML(
                            report.amount ||
                            "Not provided"
                        )}
                    </strong>

                </div>


                <div>

                    <span class="detail-label">
                        Submitted
                    </span>

                    <strong>
                        ${escapeHTML(formattedDate)}
                    </strong>

                </div>

            </div>


            <div class="report-description">

                <span class="detail-label">
                    What Happened
                </span>

                <p>
                    ${escapeHTML(
                        report.details ||
                        "No details provided."
                    )}
                </p>

            </div>


            <div class="report-actions">

                ${
                    report.link
                    ? `
                        <a
                            href="${escapeAttribute(report.link)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            🔗 Open Opportunity
                        </a>
                    `
                    : `
                        <span class="no-link">
                            No opportunity link
                        </span>
                    `
                }


                ${
                    report.email
                    ? `
                        <span>
                            📧 ${escapeHTML(report.email)}
                        </span>
                    `
                    : ""
                }


                <select
                    onchange="changeReportStatus('${escapeAttribute(report.id)}', this.value)"
                    aria-label="Change report status"
                >

                    <option
                        value="pending"
                        ${status === "pending" ? "selected" : ""}
                    >
                        Pending
                    </option>

                    <option
                        value="reviewing"
                        ${status === "reviewing" ? "selected" : ""}
                    >
                        Reviewing
                    </option>

                    <option
                        value="verified"
                        ${status === "verified" ? "selected" : ""}
                    >
                        Verified
                    </option>

                    <option
                        value="rejected"
                        ${status === "rejected" ? "selected" : ""}
                    >
                        Rejected
                    </option>

                </select>


                <button
                    type="button"
                    onclick="deleteReport('${escapeAttribute(report.id)}')"
                >
                    Delete
                </button>

            </div>

        `;


        container.appendChild(card);

    });

}


// =========================================
// STATISTICS
// =========================================

function updateStatistics(reports) {

    const totalElement =
        document.getElementById("total-reports");

    const paymentElement =
        document.getElementById("payment-reports");

    const messagingElement =
        document.getElementById("messaging-reports");

    const reviewElement =
        document.getElementById("review-reports");


    if (totalElement) {
        totalElement.textContent =
            reports.length;
    }


    if (paymentElement) {

        paymentElement.textContent =
            reports.filter(function (report) {

                const payment =
                    report.payment ||
                    report.payment_requested;

                return payment === "Yes";

            }).length;

    }


    if (messagingElement) {

        messagingElement.textContent =
            reports.filter(function (report) {

                return (
                    report.source === "WhatsApp" ||
                    report.source === "Telegram"
                );

            }).length;

    }


    if (reviewElement) {

        reviewElement.textContent =
            reports.filter(function (report) {

                return (
                    !report.status ||
                    report.status === "pending" ||
                    report.status === "reviewing"
                );

            }).length;

    }

}


// =========================================
// CHANGE REPORT STATUS
// =========================================

async function changeReportStatus(id, status) {

    if (!id) {
        return;
    }


    try {

        const response =
            await fetch(
                BACKEND_URL + "/reports/" + encodeURIComponent(id),
                {
                    method: "PATCH",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        status: status
                    })
                }
            );


        if (!response.ok) {
            throw new Error(
                "Could not update report status."
            );
        }


        loadReports();


    } catch (error) {

        console.error(
            "Status update error:",
            error
        );


        alert(
            "Could not update the report status."
        );


        loadReports();

    }

}


// =========================================
// DELETE ONE REPORT
// =========================================

async function deleteReport(id) {

    if (!id) {
        return;
    }


    if (!confirm("Delete this report?")) {
        return;
    }


    try {

        const response =
            await fetch(
                BACKEND_URL +
                "/reports/" +
                encodeURIComponent(id),
                {
                    method: "DELETE"
                }
            );


        if (!response.ok) {
            throw new Error(
                "Could not delete report."
            );
        }


        loadReports();


    } catch (error) {

        console.error(
            "Delete report error:",
            error
        );


        alert(
            "Could not delete the report."
        );

    }

}


// =========================================
// DELETE ALL REPORTS
// =========================================

async function deleteAllReports() {

    if (!confirm(
        "Are you sure you want to delete ALL reports?"
    )) {
        return;
    }


    try {

        const response =
            await fetch(
                BACKEND_URL + "/reports",
                {
                    method: "DELETE"
                }
            );


        if (!response.ok) {
            throw new Error(
                "Could not delete reports."
            );
        }


        loadReports();


    } catch (error) {

        console.error(
            "Delete all reports error:",
            error
        );


        alert(
            "Could not delete all reports."
        );

    }

}


// =========================================
// FORMAT STATUS
// =========================================

function formatStatus(status) {

    switch (status) {

        case "reviewing":
            return "REVIEWING";

        case "verified":
            return "VERIFIED";

        case "rejected":
            return "REJECTED";

        case "pending":
        default:
            return "PENDING";

    }

}


// =========================================
// SECURITY HELPERS
// =========================================

function escapeHTML(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }


    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}


function escapeAttribute(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }


    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

}
```
