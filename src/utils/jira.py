import sys

import jira


def get_issues(
    jira_client: jira.client.JIRA, project_id: str, issue_types: list[str]
) -> dict:
    result = {}
    for issue_type in issue_types:
        issues = query_issues(jira_client, project_id, issue_type)
        preprocess(jira_client, issues)
        result[issue_type] = issues
    return result


def query_issues(
    jira_client: jira.client.JIRA, project_id: str, issue_type: str
) -> dict:
    query = f"project={project_id} AND resolution=Unresolved AND type={issue_type} ORDER BY rank ASC"
    print("  ?", query)
    results = jira_client.search_issues(query, maxResults=0)
    if not results:
        print(f"No {issue_type} found via query: {query}")
        sys.exit(1)
    print("  =", f"{len(results)} results:", [r.key for r in results])
    return results


def preprocess(
    jira_client: jira.client.JIRA, issues: list[jira.resources.Issue]
) -> None:
    fields_ids = get_fields_ids(jira_client, issues)

    for issue in issues:
        issue.raw["Context"] = {}
        issue.raw["Context"]["Field Ids"] = fields_ids
        issue.raw["Context"]["Related Issues"] = {}
        issue.raw["Context"]["Related Issues"]["Parent"] = get_parent(
            jira_client, issue
        )
        issue.raw["Context"]["Related Issues"]["Blocks"] = get_blocks(
            jira_client, issue
        )


def get_fields_ids(
    jira_client: jira.client.JIRA, issues: list[jira.resources.Issue]
) -> dict[str, str]:
    ids = {}
    all_the_fields = jira_client.fields()

    link_names = ["Epic Link", "Feature Link", "Parent Link"]
    candidates = [f["id"] for f in all_the_fields if f["name"] in link_names]
    ids["Parent Link"] = get_parent_link_field_id(issues, candidates)

    ids["Rank"] = [f["id"] for f in all_the_fields if f["name"] == "Rank"][0]

    return ids


def get_parent_link_field_id(
    issues: list[jira.resources.Issue], field_ids: list[str]
) -> str:
    for issue in issues:
        for field_id in field_ids:
            if getattr(issue.fields, field_id) is not None:
                return field_id
    return ""


def get_parent(jira_client: jira.client.JIRA, issue: jira.resources.Issue):
    parent_link_field_id = issue.raw["Context"]["Field Ids"]["Parent Link"]
    if parent_link_field_id:
        parent_key = getattr(issue.fields, parent_link_field_id)
        if parent_key is not None:
            # JIRA can be flaky, so retry a few times before failing
            for _ in range(0, 5):
                try:
                    return jira_client.issue(parent_key)
                except jira.exceptions.JIRAError:
                    pass
    return None


def get_blocks(jira_client: jira.client.JIRA, issue: jira.resources.Issue):
    blocks = [
        jira_client.issue(il.raw["outwardIssue"]["key"])
        for il in issue.fields.issuelinks
        if il.type.name == "Blocks" and "outwardIssue" in il.raw.keys()
    ]
    return blocks


def refresh(issue: jira.resources.Issue) -> None:
    update(issue, {})


def update(issue: jira.resources.Issue, data: dict) -> None:
    issue_context = issue.raw.get("Context")

    # JIRA can be flaky, so retry a few times before failing
    for _ in range(0, 5):
        try:
            issue.update(**data)
            break
        except jira.exceptions.JIRAError:
            pass

    # Restore the context that was deleted by the update
    if issue_context:
        issue.raw["Context"] = issue_context
