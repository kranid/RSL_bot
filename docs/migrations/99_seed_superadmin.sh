if [ -z "${LOCAL_SUPERADMIN_TG_ID:-}" ] || [ "${LOCAL_SUPERADMIN_TG_ID}" = "PUT_YOUR_TELEGRAM_ID_HERE" ]; then
  echo "LOCAL_SUPERADMIN_TG_ID is not set; skipping local superadmin seed."
else
  echo "Seeding local superadmin ${LOCAL_SUPERADMIN_TG_ID}."
  psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=superadmin_tg_id="$LOCAL_SUPERADMIN_TG_ID" \
    --set=superadmin_username="${LOCAL_SUPERADMIN_USERNAME:-local_superadmin}" <<'EOSQL'
insert into users (tg_id, username, role, date_created, date_role_set)
values (:'superadmin_tg_id'::bigint, :'superadmin_username', 'superadmin', current_timestamp, current_timestamp)
on conflict (tg_id) do update
set username = excluded.username,
    role = 'superadmin',
    date_role_set = current_timestamp;
EOSQL
fi
