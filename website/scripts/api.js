function login(base_url, userid, password) {
    $.ajax({
        url: base_url+"/login",
        method: 'POST',
        data: JSON.stringify({ "userid": $("#userid").val(), "password": $("#password").val() }),
        processData: false,
        contentType: 'application/json',
        success: function (response) {
            return true;
        },
        error: function (xhr, status, error) {
            return false;
        }
    })
}