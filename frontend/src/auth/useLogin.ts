import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { UserSchema } from "@/api/schemas";
import { useAuth } from "./AuthContext";
import { get } from "@/api/client";

interface LoginForm {
  username: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function useLogin() {
  const { setAuth } = useAuth();

  return useMutation({
    mutationFn: async ({ username, password }: LoginForm) => {
      // fastapi-users expects form-encoded body for JWT login
      const formData = new URLSearchParams({ username, password });
      const tokenResp = await apiClient<TokenResponse>("/auth/jwt/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });

      // Fetch current user to get role/scope
      const rawUser = await get<unknown>("/auth/users/me");
      const user = UserSchema.parse(rawUser);

      setAuth(tokenResp.access_token, user);
      return user;
    },
  });
}
