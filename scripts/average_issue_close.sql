SELECT avg((
    CASE WHEN issue.closed_at IS NULL THEN datetime('now')
    ELSE issue.closed_at
    END
    ) - issue.created_at
  ) AS "average"
  FROM issue;
