begin;

create type users_role as enum ('user', 'admin', 'superadmin');

create table users (
    tg_id bigint primary key not null,
    username text,
    role users_role,
    date_created timestamp not null,
    date_role_set timestamp not null
);

end;
