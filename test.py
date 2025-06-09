from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
print(pwd_context.hash("makeakeyforme"))  # use the password you're trying

#$2b$12$0y9q1xxLepiMzQdc6/IG6eDutw1EBf8D3GX211o4/zb44j95tll/u