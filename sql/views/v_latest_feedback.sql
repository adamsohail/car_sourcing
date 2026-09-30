-- Dernier avis sur chaque annonce ; « aucun » signifie avis retiré.
SELECT * EXCEPT (rn)
FROM (
  SELECT f.*, ROW_NUMBER() OVER (PARTITION BY source, listing_id ORDER BY created_at DESC) AS rn
  FROM `${project}.${dataset}.feedback` AS f
)
WHERE rn = 1 AND status != 'aucun'
