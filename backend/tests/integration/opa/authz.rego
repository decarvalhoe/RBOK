package realison.authz

default decision = {
    "allow": false,
    "reason": "role not allowed"
}

decision = {
    "allow": true,
    "reason": "admin role required"
} {
    input.action == "procedures:create"
    input.subject.roles[_] == "app-admin"
}

decision = {
    "allow": true,
    "reason": "user role granted"
} {
    input.action == "runs:start"
    input.subject.roles[_] == "app-user"
}

decision = {
    "allow": true,
    "reason": "admin inherits run rights"
} {
    input.action == "runs:start"
    input.subject.roles[_] == "app-admin"
}

result = decision
